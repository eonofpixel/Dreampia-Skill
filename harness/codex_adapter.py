"""Optional Codex exec JSONL adapter. No raw provider output is persisted."""
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time

try:
    from .process import capture, normalize_command, popen_group_kwargs, resolve_executable, terminate
except ImportError:
    from process import capture, normalize_command, popen_group_kwargs, resolve_executable, terminate

COMPATIBLE_VERSION='0.144.6'
# Capability probes, not live provider inference certification.
CAPABILITY_VERSIONS={COMPATIBLE_VERSION,'0.161.0'}
MAX_OUTPUT=8*1024*1024
EVENTS={'thread.started','turn.started','turn.completed','turn.failed','item.started','item.updated','item.completed','error'}

def environment() -> dict[str, str]:
    result={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','SYSTEMROOT','COMSPEC','PATHEXT','TEMP','TMP','TMPDIR')}
    result['PYTHONDONTWRITEBYTECODE']='1'
    return result


def category_for(text) -> str:
    text=text.lower()
    if any(x in text for x in ('not logged in','unauthorized','authentication','401','invalid api key')): return 'AUTH_REQUIRED'
    if any(x in text for x in ('approval','permission denied','sandbox denied')): return 'APPROVAL_REQUIRED'
    if any(x in text for x in ('rate limit','429')): return 'RATE_LIMIT'
    if any(x in text for x in ('connection','network','timed out','503')): return 'NETWORK_ERROR'
    return 'CLI_ERROR'


def parse_events(raw,exit_code=0) -> dict[str, object]:
    result={'result':'FAIL','category':'PROTOCOL_ERROR','exit_code':exit_code,'protocol':'codex-exec-jsonl-v1',
            'stream_digest':hashlib.sha256(raw).hexdigest(),'event_types':[],'events':0}
    terminal=None; failed=None; types=[]
    try:
        for line in raw.decode('utf-8').splitlines():
            if not line.strip(): continue
            event=json.loads(line)
            if not isinstance(event,dict) or event.get('type') not in EVENTS: return result
            kind=event['type'];types.append(kind)
            if terminal is not None: return result # no trailing or second terminal event
            if kind in ('error','turn.failed'):
                error=event.get('error',event)
                text=error.get('message','') if isinstance(error,dict) else ''
                failed=category_for(text)
            if kind in ('turn.completed','turn.failed'):terminal=kind
    except (UnicodeError,ValueError,TypeError): return result
    result.update(event_types=sorted(set(types)),events=len(types))
    if failed: result['category']=failed
    elif exit_code!=0: result['category']='CLI_ERROR'
    elif terminal!='turn.completed': result['category']='INCOMPLETE_OUTPUT'
    else: result.update(result='PASS',category='SUCCESS')
    return result


def probe(executable='codex',timeout=5,stopped=lambda:False,lock_fd=None) -> dict[str, object]:
    if type(timeout) not in (int,float) or not 0<timeout<=3600 or not __import__('math').isfinite(timeout): raise ValueError('invalid probe bound')
    found=resolve_executable(executable)
    if not found: return {'available':False,'category':'NOT_INSTALLED','provider_calls':0}
    deadline=time.monotonic()+timeout
    try:
        def invoke(args) -> tuple[dict[str, object], dict[str, object] | None]:
            result=capture(args,environment(),max(.001,deadline-time.monotonic()),stopped,lock_fd)
            if result['reason']: return result, {'available':False,'category':'PROBE_'+result['reason'],'provider_calls':0}
            return result,None
        version,failure=invoke([found,'--version'])
        if failure:return failure
        match=re.fullmatch(r'codex-cli ([0-9]+\.[0-9]+\.[0-9]+)\s*',version['stdout'].decode('utf-8'))
        if version['exit_code'] or not match: return {'available':False,'category':'VERSION_UNKNOWN','provider_calls':0}
        value=match.group(1)
        if value not in CAPABILITY_VERSIONS: return {'available':False,'category':'UNVERIFIED_VERSION','version':value,'provider_calls':0}
        help_result,failure=invoke([found,'exec','--help'])
        if failure:return failure
        help_text=help_result['stdout'].decode('utf-8')
        if help_result['exit_code'] or any(flag not in help_text for flag in ('--json','--sandbox','--ephemeral','--ignore-user-config')):
            return {'available':False,'category':'UNSUPPORTED_FLAGS','version':value,'provider_calls':0}
        return {'available':True,'category':'READY','version':value,'provider_calls':0}
    except (OSError,UnicodeError): return {'available':False,'category':'PROBE_ERROR','provider_calls':0}


def run(config,root,timeout,stopped,lock_fd=None) -> dict[str, object]:
    began=time.monotonic(); info=probe(config.get('executable','codex'),timeout=min(timeout,5),stopped=stopped,lock_fd=lock_fd)
    if not info['available']:
        if info['category']=='PROBE_CANCELLED': return {'result':'CANCELLED','category':'CANCELLED'}
        if info['category']=='PROBE_OUTPUT_LIMIT': return {'result':'FAIL','category':'OUTPUT_LIMIT'}
        if info['category']=='PROBE_TIMEOUT': return {'result':'FAIL','category':'TIMEOUT'}
        return {'result':'NOT_RUN',**{k:v for k,v in info.items() if k!='available'}}
    if stopped(): return {'result':'CANCELLED','category':'CANCELLED','version':info['version']}
    command=normalize_command([config.get('executable','codex'),'--model',config.get('model','gpt-6.1-sol'),'-c','model_reasoning_effort=\"medium\"','--ask-for-approval','on-request','exec','--json',
             '--sandbox',config.get('sandbox','read-only'),'--ephemeral','--ignore-user-config','-'],cwd=root)
    p=None;reason=None;cleaned=False
    with tempfile.TemporaryFile() as request, tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        request.write(config['prompt'].encode('utf-8'));request.seek(0)
        try:
            p=subprocess.Popen(command,cwd=root,env=environment(),stdin=request,stdout=output,stderr=error,
                **popen_group_kwargs(lock_fd))
            while p.poll() is None:
                if stopped():reason='CANCELLED';break
                if time.monotonic()-began>=timeout:reason='TIMEOUT';break
                if os.fstat(output.fileno()).st_size+os.fstat(error.fileno()).st_size>MAX_OUTPUT:reason='OUTPUT_LIMIT';break
                time.sleep(.02)
            terminate(p);cleaned=True
            output.seek(0);error.seek(0);raw=output.read(MAX_OUTPUT+1);errors=error.read(MAX_OUTPUT+1)
            if len(raw)+len(errors)>MAX_OUTPUT:reason='OUTPUT_LIMIT'
            if reason: result={'result':'CANCELLED' if reason=='CANCELLED' else 'FAIL','category':reason,'exit_code':p.returncode}
            else:
                result=parse_events(raw,p.returncode)
                if result['category'] in ('CLI_ERROR','INCOMPLETE_OUTPUT') and errors:
                    result['category']=category_for(errors.decode('utf-8',errors='replace'))
            result.update(version=info['version'],duration=round(time.monotonic()-began,4))
            return result
        except OSError: return {'result':'NOT_RUN','category':'EXEC_ERROR','version':info['version']}
        finally:
            if p is not None and not cleaned: terminate(p)
