"""Small cross-platform orchestration engine. No sandbox or AI API is provided."""
import contextlib
try:
    from .schema import loads
    from . import process as _proc
except ImportError:
    from schema import loads
    import process as _proc
import datetime
import hashlib
import json
import math
import os
import pathlib
import re
import signal
import stat
import subprocess
import time
import tempfile
import uuid
import unicodedata

ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
ROOT_RUNTIME = {'.harness', '.git'}

def fields(value, allowed, required=()) -> None:
    if not isinstance(value,dict) or set(value)-set(allowed) or set(required)-set(value):
        raise ValueError('unknown or missing field')

def identifiers(value) -> bool:
    return isinstance(value,list) and all(isinstance(x,str) and ID.fullmatch(x) for x in value) and len(set(value))==len(value)



class StateError(ValueError):
    code = 'STATE_CORRUPT'


class SourceError(ValueError):
    code = 'SOURCE_UNSAFE'


def relative_input(value) -> str:
    if not isinstance(value,str) or not value or '\x00' in value:
        raise ValueError('invalid input path')
    p=pathlib.PurePosixPath(value)
    if p.is_absolute() or any(x in ('..','') for x in p.parts) or not p.parts or p.parts[0] in ROOT_RUNTIME:
        raise ValueError('input path escapes source scope')
    return value



def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def argv(value) -> None:
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x or '\x00' in x for x in value):
        raise ValueError('argv must be a nonempty string array')


def validate(m) -> dict[str, object]:
    fields(m, ('version','requirements','tasks'), ('version','requirements','tasks'))
    if type(m.get('version')) is not int or m.get('version') != 1 or not isinstance(m.get('tasks'), list) or not m['tasks']:
        raise ValueError('version 1 and nonempty tasks required')
    req = m.get('requirements', [])
    if not identifiers(req) or not req:
        raise ValueError('unique requirement IDs required')
    tasks = m['tasks']
    if any(not isinstance(t,dict) for t in tasks): raise ValueError('task must be an object')
    for t in tasks: fields(t, ('id','requirements','depends_on','max_attempts','timeout','adapter','checks','owner','owns'), ('id','requirements','adapter','checks'))
    ids = [t['id'] for t in tasks]
    if not identifiers(ids):
        raise ValueError('unique task IDs required')
    checks = set(); covered = set(); ownership = []
    for t in tasks:
        if ('owner' in t)!=('owns' in t):raise ValueError('owner and owns must be paired')
        if 'owner' in t:
            if not isinstance(t['owner'],str) or not ID.fullmatch(t['owner']) or not isinstance(t['owns'],list) or not t['owns']:raise ValueError('invalid ownership')
            paths=[]
            for value in t['owns']:
                relative_input(value)
                if pathlib.PurePosixPath(value).as_posix()!=value:raise ValueError('noncanonical ownership path')
                identity=unicodedata.normalize('NFC',value).casefold()
                if identity in paths:raise ValueError('duplicate ownership path')
                paths.append(identity)
                for old,other in ownership:
                    if identity==old or identity.startswith(old+'/') or old.startswith(identity+'/'):raise ValueError('overlapping task ownership')
            ownership.extend((value,t['id']) for value in paths)
        links = t.get('requirements', [])
        if not identifiers(links) or not links or any(x not in req for x in links):
            raise ValueError('task requirement link missing')
        covered.update(links)
        deps = t.get('depends_on', [])
        if not identifiers(deps) or any(x not in ids or x == t['id'] for x in deps):
            raise ValueError('invalid dependency')
        for k, default, maximum in [('max_attempts', 2, 10), ('timeout', 30, 3600)]:
            v=t.get(k, default)
            if isinstance(v,bool) or not isinstance(v,(float,int)) or v <= 0 or v > maximum or not math.isfinite(v) or (k=='max_attempts' and not isinstance(v,int)):
                raise ValueError('invalid execution bound')
        a = t.get('adapter', {})
        if not isinstance(a,dict): raise ValueError('adapter must be an object')
        if a.get('kind') == 'command':
            fields(a, ('kind','argv'), ('kind','argv')); argv(a.get('argv'))
        elif a.get('kind') == 'codex':
            fields(a, ('kind','sandbox','executable','retry_policy','prompt','model','reasoning_effort'), ('kind','prompt'))
            if a.get('model','gpt-6.1-sol')!='gpt-6.1-sol' or a.get('reasoning_effort','medium')!='medium': raise ValueError('team model policy mismatch')
            if a.get('sandbox','read-only') not in ('read-only','workspace-write'):
                raise ValueError('unsafe sandbox')
            if not isinstance(a.get('executable','codex'),str) or not a.get('executable','codex') or '\x00' in a.get('executable','codex'):
                raise ValueError('invalid executable')
            if a.get('retry_policy','never') not in ('never','transient'): raise ValueError('invalid provider retry policy')
            if not isinstance(a.get('prompt',''),str) or not a.get('prompt','').strip():
                raise ValueError('codex prompt required')
        elif a.get('kind') == 'deterministic':
            fields(a, ('kind','fail_attempts','delay'), ('kind',))
            if type(a.get('fail_attempts',0)) is not int or not 0 <= a.get('fail_attempts',0) <= 10:
                raise ValueError('invalid mock failures')
            delay=a.get('delay',0)
            if type(delay) not in (int,float) or not 0 <= delay <= 3600 or not math.isfinite(delay):
                raise ValueError('invalid mock delay')
        else: raise ValueError('unknown adapter')
        if not isinstance(t.get('checks'),list) or not t['checks']: raise ValueError('verification must run')
        for c in t['checks']:
            if not isinstance(c,dict): raise ValueError('check must be an object')
            fields(c, ('id','argv','inputs'), ('id','argv'))
            if not isinstance(c['id'],str) or not ID.fullmatch(c['id']) or c['id'] in checks: raise ValueError('unique check IDs required')
            checks.add(c['id']); argv(c.get('argv'))
            inputs=c.get('inputs',[])
            if not isinstance(inputs,list): raise ValueError('inputs must be a list')
            for value in inputs: relative_input(value)
    if covered != set(req): raise ValueError('uncovered requirement')
    visited=set(); visiting=set(); byid={t['id']:t for t in tasks}
    def visit(i) -> None:
        if i in visiting: raise ValueError('dependency cycle')
        if i in visited: return
        visiting.add(i)
        for d in byid[i].get('depends_on',[]): visit(d)
        visiting.remove(i); visited.add(i)
    for i in ids: visit(i)
    return m


def load(root) -> dict[str, object]:
    return validate(loads((root/'harness.json').read_text()))


def source_hash(root) -> str:
    """Directory-fd traversal prevents symlink escape; not an atomic tree snapshot."""
    root=pathlib.Path(root).resolve();h=hashlib.sha256()
    key=lambda v:(v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
    if os.name=='nt' or not hasattr(os,'O_DIRECTORY'):
        def walk_win(cur_dir,parts) -> None:
            if _proc.is_symlink_path(cur_dir):raise SourceError('source symlinks unsupported')
            before_dir=os.stat(cur_dir,follow_symlinks=False)
            h.update(b'D\0'+('/'.join(parts) or '.').encode()+b'\0'+str(_proc.effective_imode(cur_dir,before_dir.st_mode)).encode()+b'\0')
            entries=sorted(os.scandir(cur_dir),key=lambda x:x.name)
            for entry in entries:
                rel=parts+(entry.name,)
                entry_path=cur_dir/entry.name
                if _proc.is_symlink_path(entry_path):raise SourceError('source symlinks unsupported')
                info=entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):raise SourceError('source symlinks unsupported')
                if len(rel)==1 and entry.name in ROOT_RUNTIME:continue
                if stat.S_ISDIR(info.st_mode):
                    walk_win(entry_path,rel)
                elif stat.S_ISREG(info.st_mode):
                    fd=os.open(str(entry_path),os.O_RDONLY|getattr(os,'O_BINARY',0))
                    try:
                        before=os.fstat(fd)
                        if not stat.S_ISREG(before.st_mode) or before.st_size!=info.st_size or before.st_mtime_ns!=info.st_mtime_ns:raise SourceError('source entry changed')
                        content=hashlib.sha256()
                        while True:
                            chunk=os.read(fd,1024*1024)
                            if not chunk:break
                            content.update(chunk)
                        after=os.fstat(fd);path_now=os.stat(entry_path,follow_symlinks=False)
                        if before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns or after.st_mtime_ns!=path_now.st_mtime_ns:raise SourceError('source changed while hashing')
                        h.update(b'F\0'+'/'.join(rel).encode()+b'\0');h.update(str(_proc.effective_imode(entry_path,before.st_mode)).encode()+b'\0');h.update(content.digest())
                    finally:os.close(fd)
                else:raise SourceError('special source files unsupported')
        walk_win(root,())
        return h.hexdigest()
    def walk(directory_fd,parts) -> None:
        before_dir=os.fstat(directory_fd)
        h.update(b'D\0'+('/'.join(parts) or '.').encode()+b'\0'+str(stat.S_IMODE(before_dir.st_mode)).encode()+b'\0')
        entries=sorted(os.scandir(directory_fd),key=lambda x:x.name)
        for entry in entries:
            rel=parts+(entry.name,)
            info=os.stat(entry.name,dir_fd=directory_fd,follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):raise SourceError('source symlinks unsupported')
            if len(rel)==1 and entry.name in ROOT_RUNTIME:continue
            if stat.S_ISDIR(info.st_mode):
                child=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory_fd)
                try:walk(child,rel)
                finally:os.close(child)
            elif stat.S_ISREG(info.st_mode):
                fd=os.open(entry.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory_fd)
                try:
                    before=os.fstat(fd)
                    if not stat.S_ISREG(before.st_mode) or key(before)!=key(info):raise SourceError('source entry changed')
                    content=hashlib.sha256()
                    while True:
                        chunk=os.read(fd,1024*1024)
                        if not chunk:break
                        content.update(chunk)
                    after=os.fstat(fd);path_now=os.stat(entry.name,dir_fd=directory_fd,follow_symlinks=False)
                    if key(before)!=key(after) or key(after)!=key(path_now):raise SourceError('source changed while hashing')
                    h.update(b'F\0'+'/'.join(rel).encode()+b'\0');h.update(str(stat.S_IMODE(before.st_mode)).encode()+b'\0');h.update(content.digest())
                finally:os.close(fd)
            else:raise SourceError('special source files unsupported')
        if key(before_dir)!=key(os.fstat(directory_fd)):raise SourceError('source directory changed while hashing')
    fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:walk(fd,())
    finally:os.close(fd)
    return h.hexdigest()


def check_inputs(root,m) -> None:
    for t in m['tasks']:
        for c in t['checks']:
            for value in c.get('inputs',[]):
                p=root/relative_input(value)
                for ancestor in [p,*p.parents]:
                    if ancestor==root.parent: break
                    if ancestor.is_symlink(): raise SourceError('input symlink')
                    if ancestor==root: break
                if not p.is_file(): raise SourceError('declared input missing')


def atomic(path, value) -> None:
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('x') as f:
            os.chmod(tmp,0o600); json.dump(value,f,sort_keys=True,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
        _proc.fsync_dir(path.parent)
    finally:
        if tmp.exists(): tmp.unlink()


def state_dir(root) -> pathlib.Path:
    d=root/'.harness'
    if d.is_symlink(): raise ValueError('state directory cannot be a symlink')
    d.mkdir(mode=0o700,exist_ok=True)
    for name in ['lock','state.json','state.backup.json','events.jsonl','cancel.json','quarantine']:
        if (d/name).is_symlink(): raise ValueError('state symlinks unsupported')
    return d


@contextlib.contextmanager
def locked(d) -> object:
    try: fd=_proc.acquire_lock(d/'lock')
    except BlockingIOError: raise RuntimeError('another runner owns this project')
    try: yield fd
    finally: _proc.release_lock(fd)


def initial(m) -> dict[str, object]:
    return {'version':2,'manifest':digest(m),'tasks':{t['id']:{'status':'pending','attempts':0} for t in m['tasks']}}


def validate_state(s) -> dict[str, object]:
    def fail() -> None:raise StateError('invalid state schema')
    def hash_value(v) -> bool:return isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) is not None
    def timestamp(v) -> bool:
        try:return isinstance(v,str) and datetime.datetime.fromisoformat(v).utcoffset() is not None
        except (ValueError,TypeError):return False
    def proofs(value) -> None:
        if not isinstance(value,list):fail()
        for c in value:
            if not isinstance(c,dict) or set(c)!={'id','result','exit_code','duration','at','argv_digest'}:fail()
            if not isinstance(c['id'],str) or not ID.fullmatch(c['id']) or not hash_value(c['argv_digest']):fail()
            if c['result'] not in ('PASS','FAIL','NOT_RUN','TIMEOUT','CANCELLED'):fail()
            if c['exit_code'] is not None and type(c['exit_code']) is not int:fail()
            if type(c['duration']) not in (int,float) or not 0<=c['duration']<=86400 or not math.isfinite(c['duration']) or not timestamp(c['at']):fail()
    if not isinstance(s,dict) or set(s)!={'version','manifest','tasks'} or type(s['version']) is not int or s['version'] not in (1,2) or not hash_value(s['manifest']) or not isinstance(s['tasks'],dict):fail()
    statuses=('pending','running','verifying','verified','failed','cancelled','blocked','stale','recovery_hold')
    for i,q in s['tasks'].items():
        if not isinstance(i,str) or not ID.fullmatch(i) or not isinstance(q,dict) or set(q)-{'status','attempts','evidence','last_checks','reason','replay_required','adapter_evidence'} or q.get('status') not in statuses:fail()
        if type(q.get('attempts')) is not int or not 0<=q['attempts']<=10:fail()
        if 'replay_required' in q and type(q['replay_required']) is not bool:fail()
        if 'reason' in q and q['reason'] not in ('source_changed_during_checks','invalid_source_inputs','provider_not_authorized'):fail()
        if 'last_checks' in q:proofs(q['last_checks'])
        if q['status']=='verified' and 'evidence' not in q:fail()
        if 'evidence' in q:
            e=q['evidence']
            if not isinstance(e,dict) or set(e)!={'source','checks_digest','checks','at','run'} or not hash_value(e['source']) or not hash_value(e['checks_digest']) or not timestamp(e['at']) or not isinstance(e['run'],str) or not re.fullmatch('[0-9a-f]{32}',e['run']):fail()
            proofs(e['checks'])
        if 'adapter_evidence' in q:
            e=q['adapter_evidence'];categories=('SUCCESS','PROTOCOL_ERROR','CLI_ERROR','INCOMPLETE_OUTPUT','AUTH_REQUIRED','APPROVAL_REQUIRED','RATE_LIMIT','NETWORK_ERROR','NOT_INSTALLED','VERSION_UNKNOWN','UNVERIFIED_VERSION','UNSUPPORTED_FLAGS','PROBE_TIMEOUT','PROBE_CANCELLED','PROBE_OUTPUT_LIMIT','PROBE_ERROR','TIMEOUT','CANCELLED','OUTPUT_LIMIT','EXEC_ERROR')
            if not isinstance(e,dict) or set(e)-{'result','category','exit_code','event_types','stream_digest','events','version','protocol'} or e.get('result') not in ('PASS','FAIL','NOT_RUN','CANCELLED') or e.get('category') not in categories:fail()
            if 'version' in e and (not isinstance(e['version'],str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',e['version'])):fail()
            if 'stream_digest' in e and not hash_value(e['stream_digest']):fail()
            if 'events' in e and (type(e['events']) is not int or e['events']<0):fail()
            if 'exit_code' in e and e['exit_code'] is not None and type(e['exit_code']) is not int:fail()
            if 'protocol' in e and e['protocol']!='codex-exec-jsonl-v1':fail()
            if 'event_types' in e and (not isinstance(e['event_types'],list) or any(x not in ('thread.started','turn.started','turn.completed','turn.failed','item.started','item.updated','item.completed','error') for x in e['event_types'])):fail()
    return s


def read_json_state(path) -> dict[str, object]:
    try: return validate_state(loads(path.read_text()))
    except (ValueError,TypeError,KeyError,AttributeError,UnicodeError) as exc:
        raise StateError('state needs explicit recovery') from exc


def read_state(d,m) -> dict[str, object]:
    s=read_json_state(d/'state.json') if (d/'state.json').exists() else initial(m)
    if s['manifest']!=digest(m):
        previous=s;s=initial(m)
        for t in m['tasks']:
            s['tasks'][t['id']]={'status':'recovery_hold','attempts':previous['tasks'].get(t['id'],{}).get('attempts',t.get('max_attempts',2)),'replay_required':True}
    if set(s['tasks'])!={t['id'] for t in m['tasks']}: raise StateError('invalid state tasks')
    return s


def save_state(d,s) -> None:
    validate_state(s)
    if (d/'state.json').exists():
        previous=read_json_state(d/'state.json')
        atomic(d/'state.backup.json',previous)
    atomic(d/'state.json',s)


def recover(root) -> dict[str, object]:
    root=pathlib.Path(root).resolve();m=load(root);d=state_dir(root)
    with locked(d):
        previous=None
        for name in ('state.json','state.backup.json'):
            if (d/name).exists():
                try:
                    candidate=read_json_state(d/name)
                    if candidate['manifest']==digest(m) and previous is None: previous=candidate
                except StateError: pass
        quarantine=d/'quarantine'/uuid.uuid4().hex
        quarantine.mkdir(parents=True,mode=0o700)
        for name in ('state.json','state.backup.json'):
            if (d/name).exists():
                target=quarantine/name
                with target.open('xb') as f:
                    os.chmod(target,0o600); f.write((d/name).read_bytes());f.flush();os.fsync(f.fileno())
        s=initial(m)
        for t in m['tasks']:
            old=previous['tasks'].get(t['id'],{}) if previous else {}
            s['tasks'][t['id']]={'status':'recovery_hold','attempts':old.get('attempts',t.get('max_attempts',2)), 'replay_required':True}
        atomic(d/'state.json',s) # never resurrect historical completion
        atomic(d/'state.backup.json',s)
        return {'recovered':True,'status':'recovery_hold','quarantine':str(quarantine.relative_to(root)), 'provider_calls':0}


def authorize_replay(root,task,accept_side_effects=False) -> dict[str, object]:
    if not accept_side_effects: raise ValueError('explicit side effect acknowledgment required')
    root=pathlib.Path(root).resolve();m=load(root);d=state_dir(root)
    with locked(d):
        s=read_state(d,m)
        if task not in s['tasks'] or not s['tasks'][task].get('replay_required'): raise ValueError('task is not held for recovery')
        s['tasks'][task]={'status':'pending','attempts':0}
        save_state(d,s)
    return {'authorized_task':task,'status':'pending','executed':False}


def reverify(root) -> dict[str, object]:
    return run(root,reverify_only=True)


def fresh(q,t,source) -> bool:
    e=q.get('evidence',{})
    if not isinstance(e,dict): return False
    checks=e.get('checks',[])
    if not isinstance(checks,list) or len(checks)!=len(t['checks']): return False
    valid=all(isinstance(proof,dict) and proof.get('id')==expected['id']
              and proof.get('argv_digest')==digest(expected['argv'])
              and proof.get('result')=='PASS' and proof.get('exit_code')==0
              for proof,expected in zip(checks,t['checks']))
    return q['status']=='verified' and e.get('source')==source and e.get('checks_digest')==digest(t['checks']) and valid


def status(root) -> dict[str, object]:
    root=pathlib.Path(root).resolve(); m=load(root); d=state_dir(root); s=read_state(d,m); src=source_hash(root)
    for t in m['tasks']:
        q=s['tasks'][t['id']]
        if q['status']=='verified' and not fresh(q,t,src): q['status']='stale'
    return s


def cancel(root) -> None:
    d=state_dir(pathlib.Path(root).resolve()); atomic(d/'cancel.json',{'requested':now()})


def execute(command, root, timeout, stopped, context=None, lock_fd=None) -> dict[str, object]:
    """No output persistence. argv/stdout/stderr can contain secrets."""
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','SYSTEMROOT','COMSPEC','PATHEXT','TEMP','TMP','TMPDIR')}
    env['PYTHONDONTWRITEBYTECODE']='1'
    norm_cmd=_proc.normalize_command(command,cwd=root)
    with tempfile.TemporaryFile() as request:
        if context is not None:
            request.write(json.dumps(context).encode()); request.seek(0)
        p=subprocess.Popen(norm_cmd,cwd=root,env=env,stdin=request if context is not None else subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**_proc.popen_group_kwargs(lock_fd))
    start=time.monotonic(); reason=None
    while p.poll() is None:
        if stopped(): reason='CANCELLED'; break
        if time.monotonic()-start >= timeout: reason='TIMEOUT'; break
        time.sleep(.02)
    _proc.terminate(p)
    return {'result':reason or ('PASS' if p.returncode==0 else 'FAIL'),'exit_code':p.returncode,'duration':round(time.monotonic()-start,4)}


def run(root, retry_failed=False, reverify_only=False, allow_provider=False) -> dict[str, object]:
    root=pathlib.Path(root).resolve(); m=load(root); d=state_dir(root)
    with locked(d) as lock_fd:
        if (d/'cancel.json').exists(): (d/'cancel.json').unlink() # explicit run resumes cancellation
        s=read_state(d,m); run_id=uuid.uuid4().hex; interrupted=[False]
        previous={}
        if __import__('threading').current_thread() is __import__('threading').main_thread():
            for sig in (signal.SIGINT,signal.SIGTERM):
                previous[sig]=signal.signal(sig,lambda *_:interrupted.__setitem__(0,True))
        def stopped() -> bool: return interrupted[0] or (d/'cancel.json').exists()
        def save() -> None: save_state(d,s)
        def event(kind,task=None,**fields) -> None:
            # Only fixed, allowlisted metadata. No command/context/output/error text.
            row={'at':now(),'run':run_id,'event':kind,**fields}
            if task: row['task']=task
            with (d/'events.jsonl').open('a') as f:
                os.chmod(d/'events.jsonl',0o600); f.write(json.dumps(row)+'\n'); f.flush(); os.fsync(f.fileno())
        def verify(t,q) -> bool:
            q['status']='verifying'; q.pop('evidence',None); save()
            try:
                check_inputs(root,{'tasks':[t]});src=source_hash(root)
            except (ValueError,OSError):
                q['status']='failed';q['reason']='invalid_source_inputs';save();return False
            results=[]
            for c in t['checks']:
                if stopped(): q['status']='cancelled'; save(); return False
                began=now()
                try: result=execute(c['argv'],root,t.get('timeout',30),stopped,lock_fd=lock_fd)
                except OSError: result={'result':'NOT_RUN','exit_code':None,'duration':0}
                result.update({'id':c['id'],'at':began,'argv_digest':digest(c['argv'])}); results.append(result)
                event('check',t['id'],check=c['id'],result=result['result'],exit_code=result['exit_code'])
                if result['result']!='PASS':
                    q['status']='cancelled' if result['result']=='CANCELLED' else 'failed'
                    q['last_checks']=results; save(); return False
            try: after=source_hash(root)
            except (ValueError,OSError): after=None
            if src != after:
                q['status']='failed'; q['reason']='source_changed_during_checks'; save(); event('unstable_source',t['id']); return False
            q['evidence']={'source':src,'checks_digest':digest(t['checks']),'checks':results,'at':now(),'run':run_id}
            q['status']='verified'; q.pop('last_checks',None); save(); event('verified',t['id'],source=src); return True
        try:
            event('start'); src=source_hash(root)
            for t in m['tasks']:
                q=s['tasks'][t['id']]
                if reverify_only: q['status']='stale'
                if q['status']=='verified' and not fresh(q,t,src): q['status']='stale'
                if q['status'] in ('running','verifying','cancelled','blocked'): q['status']='pending'
                if retry_failed and q['status']=='failed' and not q.get('replay_required'):
                    q['status']='pending'; q['attempts']=0; event('retry_budget_reset',t['id'])
            save()
            remaining={t['id']:t for t in m['tasks'] if s['tasks'][t['id']]['status']!='verified'}
            while remaining and not stopped():
                progressed=False
                for i,t in list(remaining.items()):
                    q=s['tasks'][i]
                    if q.get('replay_required') and not reverify_only:
                        q['status']='recovery_hold'; del remaining[i]; continue
                    if q['status']=='failed': del remaining[i]; continue
                    if t['adapter']['kind']=='codex' and not allow_provider and not reverify_only and q['status']!='stale':
                        q['status']='blocked';q['reason']='provider_not_authorized';del remaining[i];continue
                    if any(s['tasks'][dep]['status']!='verified' for dep in t.get('depends_on',[])): continue
                    progressed=True; del remaining[i]
                    # Stale successful work is reverified, without repeating adapter edits.
                    if q['status']=='stale': verify(t,q); continue
                    while q['attempts'] < t.get('max_attempts',2) and not stopped():
                        q['attempts']+=1; q['status']='running'; q.pop('evidence',None); save(); event('attempt',i,attempt=q['attempts'])
                        a=t['adapter']; timeout=t.get('timeout',30)
                        if a['kind']=='deterministic':
                            began=time.monotonic()
                            while time.monotonic()-began < min(a.get('delay',0),timeout) and not stopped(): time.sleep(.02)
                            result={'result':'CANCELLED' if stopped() else 'TIMEOUT' if a.get('delay',0)>timeout else 'FAIL' if q['attempts']<=a.get('fail_attempts',0) else 'PASS'}
                        elif a['kind']=='codex':
                            try:
                                from . import codex_adapter
                            except ImportError:
                                import codex_adapter
                            result=codex_adapter.run(a,root,timeout,stopped,lock_fd)
                            q['adapter_evidence']={k:v for k,v in result.items() if k in ('result','category','exit_code','event_types','stream_digest','events','version','protocol')}
                        else:
                            context={'protocol':1,'task':t,'project':str(root),'attempt':q['attempts'],'idempotency_key':s['manifest']+':'+i}
                            try: result=execute(a['argv'],root,timeout,stopped,context,lock_fd=lock_fd)
                            except OSError: result={'result':'NOT_RUN'}
                        event('adapter',i,result=result['result'])
                        if result['result']=='PASS':
                            if verify(t,q): break
                        elif result['result']=='CANCELLED': q['status']='cancelled'; save(); break
                        else: q['status']='failed'; save()
                        if a['kind']=='codex' and (a.get('retry_policy','never')!='transient' or result.get('category') not in ('NETWORK_ERROR','RATE_LIMIT')): break
                    if stopped(): q['status']='cancelled'; save(); break
                    if q['status']!='verified': q['status']='failed'; save()
                if not progressed: break
            for i in remaining:
                s['tasks'][i]['status']='cancelled' if stopped() else 'blocked'
            # Later adapter edits invalidate earlier source proofs. Recheck the whole final source.
            if not stopped():
                final_source=source_hash(root)
                for t in m['tasks']:
                    q=s['tasks'][t['id']]
                    if q['status']=='verified' and not fresh(q,t,final_source): verify(t,q)
                for _ in m['tasks']:
                    for t in m['tasks']:
                        q=s['tasks'][t['id']]
                        if q['status']=='verified' and (not fresh(q,t,source_hash(root)) or any(s['tasks'][dep]['status']!='verified' for dep in t.get('depends_on',[]))):
                            q['status']='blocked'; q.pop('evidence',None)
            save(); event('end',complete=all(q['status']=='verified' for q in s['tasks'].values()))
            return s
        finally:
            for sig,handler in previous.items(): signal.signal(sig,handler)


def trace(root) -> list[dict[str, object]]:
    root=pathlib.Path(root).resolve(); m=load(root); s=status(root); rows=[]
    for t in m['tasks']:
        q=s['tasks'][t['id']]; e=q.get('evidence',{})
        for r in t['requirements']:
            for c in t['checks']:
                proof=next((x for x in e.get('checks',[]) if x.get('id')==c['id']),{})
                rows.append({'requirement':r,'task':t['id'],'check':c['id'],
                             'status':q['status'],'result':proof.get('result','NOT_RUN'),
                             'current':fresh(q,t,source_hash(root)), 'source':e.get('source'),
                             'evidence_path':'.harness/state.json#/tasks/'+t['id']+'/evidence'})
    return rows
