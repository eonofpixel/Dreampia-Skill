#!/usr/bin/env python3
"""Explicit project-scoped installer. Standard library, offline, no hooks."""
import argparse
try:
    from .schema import loads
except ImportError:
    from schema import loads
import base64
import contextlib
import hashlib
import json
import os
import pathlib
import stat
import sys
import uuid
try:
    from . import autopilot_engine, process as _proc, reconstruct_engine, route_planner, sdd_engine, skill_bundle, universal_router, visual_acceptance, write_boundary
except ImportError:
    import autopilot_engine, process as _proc, reconstruct_engine, route_planner, sdd_engine, skill_bundle, universal_router, visual_acceptance, write_boundary

VERSION='0.6.1'
PACKAGE=pathlib.Path(__file__).resolve().parents[1]
META='.dreampia-install'
SKILL='.agents/skills/ai-dev-execution/'
FIXED={'.dreampia/team.json','.dreampia/project.json','.dreampia/WORK_CONTRACT.ko.md','.dreampia/codex.ko.md'}

class InstallError(ValueError):
    code='INSTALL_INPUT_INVALID'

class Conflict(InstallError):
    code='INSTALL_CONFLICT'


def exact(value, keys) -> None:
    if not isinstance(value,dict) or set(value)!=set(keys): raise InstallError('unknown or missing field')


def canonical(value) -> bytes:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2).encode()+b'\n'


def sha(data) -> str:return hashlib.sha256(data).hexdigest()


def managed_name(name) -> str:
    if not isinstance(name,str) or not name or '\x00' in name or '\\' in name:raise InstallError('invalid path')
    parts=pathlib.PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or parts.as_posix()!=name:raise InstallError('path escape')
    if name not in FIXED and not (name.startswith(SKILL) and len(name)>len(SKILL)):raise InstallError('unmanaged path')
    return name


def safe(root,name) -> pathlib.Path:
    path=root/name
    for p in [path,*path.parents]:
        if p==root.parent:break
        if p.is_symlink():raise InstallError('symlink unsupported')
        if p.exists() and p!=path and not p.is_dir():raise InstallError('parent must be directory')
        if p==root:break
    return path


def read_bytes(root,name) -> bytes | None:
    p=safe(root,name)
    if not p.exists():return None
    if not p.is_file() or not stat.S_ISREG(p.stat().st_mode):raise InstallError('regular file required')
    return p.read_bytes()


def write_bytes(root,name,data) -> None:
    p=safe(root,name)
    if data is None:
        if p.exists():p.unlink()
        return
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as f:
            os.chmod(tmp,0o600);f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
        _proc.fsync_dir(p.parent)
    finally:
        if tmp.exists():tmp.unlink()


def validate_policy(data) -> None:
    exact(data,('schema_version','model','reasoning_effort','automatic_model_upgrade','executor_count','max_review_rounds','parallel_policy'))
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['model']!='gpt-6.1-sol' or data['reasoning_effort']!='medium' or data['automatic_model_upgrade'] is not False or type(data['executor_count']) is not int or data['executor_count']!=1 or type(data['max_review_rounds']) is not int or not 1<=data['max_review_rounds']<=2 or data['parallel_policy']!='explicit_independent_owned_tasks_only':raise InstallError('invalid team policy')


def validate_project(data) -> None:
    exact(data,('schema_version','host_adapter','raw_output','provider_enabled'))
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['host_adapter']!='codex' or data['raw_output']!='discard' or type(data['provider_enabled']) is not bool:raise InstallError('invalid project config')
    # This setting is informative. Every provider run still requires --allow-provider.


def payload(source=PACKAGE) -> dict[str, bytes]:
    source=pathlib.Path(source).resolve();result={}
    skill=source/'ai-dev-execution'
    if skill.is_symlink() or not skill.is_dir():raise InstallError('skill missing')
    for p in sorted(skill.rglob('*')):
        if p.is_symlink():raise InstallError('source symlink')
        if p.is_file():result[SKILL+p.relative_to(skill).as_posix()]=p.read_bytes()
        elif not p.is_dir():raise InstallError('source special file')
    if SKILL+'SKILL.md' not in result:raise InstallError('skill entry missing')
    try:
        if read_bytes(source,'VERSION').decode().strip()!=VERSION:raise ValueError('source/runtime version mismatch')
        skill_bundle.validate({n[len(SKILL):]:data for n,data in result.items()},VERSION)
    except (ValueError,AttributeError,UnicodeError) as exc:raise InstallError(str(exc)) from exc
    for target,origin in [('.dreampia/team.json','team/policy.json'),('.dreampia/project.json','team/project.json'),('.dreampia/WORK_CONTRACT.ko.md','team/WORK_CONTRACT.ko.md'),('.dreampia/codex.ko.md','adapters/codex.ko.md')]:
        result[target]=read_bytes(source,origin)
        if result[target] is None:raise InstallError('source file missing')
    validate_policy(loads(result['.dreampia/team.json']));validate_project(loads(result['.dreampia/project.json']))
    for name in result:managed_name(name)
    return result


def manifest(version,files) -> dict[str, object]:
    return {'schema_version':1,'package_version':version,'files':{k:sha(v) for k,v in sorted(files.items())}}


def validate_manifest(value) -> dict[str, object]:
    exact(value,('schema_version','package_version','files'))
    if type(value['schema_version']) is not int or value['schema_version']!=1 or not isinstance(value['package_version'],str) or not __import__('re').fullmatch(r'\d+\.\d+\.\d+',value['package_version']) or not isinstance(value['files'],dict):raise InstallError('invalid manifest')
    for name,digest in value['files'].items():
        managed_name(name)
        if not isinstance(digest,str) or not __import__('re').fullmatch('[0-9a-f]{64}',digest):raise InstallError('invalid digest')
    return value


def load_manifest(root) -> dict[str, object] | None:
    raw=read_bytes(root,META+'/manifest.json')
    return validate_manifest(loads(raw)) if raw is not None else None


def encode(data) -> str | None:return None if data is None else base64.b64encode(data).decode('ascii')
def decode(value) -> bytes | None:
    if value is None:return None
    if not isinstance(value,str):raise InstallError('invalid backup')
    try:return base64.b64decode(value,validate=True)
    except ValueError:raise InstallError('invalid backup')


def journal(root,name) -> dict[str, object] | None:
    raw=read_bytes(root,META+'/'+name)
    if raw is None:return None
    value=loads(raw);exact(value,('schema_version','before','after','files'))
    if type(value['schema_version']) is not int or value['schema_version']!=1 or not isinstance(value['files'],dict):raise InstallError('invalid journal')
    for m in (value['before'],value['after']):
        if m is not None:validate_manifest(m)
    expected=set((value['before'] or {'files':{}})['files'])|set((value['after'] or {'files':{}})['files'])
    if set(value['files'])!=expected:raise InstallError('journal scope mismatch')
    for key,row in value['files'].items():
        managed_name(key);exact(row,('before','after'))
        for side in ('before','after'):
            data=decode(row[side]);m=value[side]
            digest=(m or {'files':{}})['files'].get(key)
            if (data is None)!=(digest is None) or data is not None and sha(data)!=digest:raise InstallError('journal hash mismatch')
    return value


def conflicts(root,current) -> list[str]:
    return [k for k,v in (current or {'files':{}})['files'].items() if (lambda b:b is None or sha(b)!=v)(read_bytes(root,k))]


def prune_empty(root,names) -> None:
    dirs=set()
    for name in names:
        p=(root/name).parent
        while p!=root:
            dirs.add(p);p=p.parent
    for p in sorted(dirs,key=lambda p:len(p.parts),reverse=True):
        try:p.rmdir()
        except OSError:pass


@contextlib.contextmanager
def locked(root) -> object:
    d=safe(root,META);d.mkdir(mode=0o700,exist_ok=True)
    p=safe(root,META+'/lock')
    try:fd=_proc.acquire_lock(p)
    except BlockingIOError:raise Conflict('installer already running')
    try:yield
    finally:_proc.release_lock(fd)


def transaction(root,current,desired,version) -> None:
    previous={k:read_bytes(root,k) for k in (current or {'files':{}})['files']}
    after=manifest(version,desired)
    names=set(previous)|set(desired)
    record={'schema_version':1,'before':current,'after':after,'files':{k:{'before':encode(previous.get(k)),'after':encode(desired.get(k))} for k in sorted(names)}}
    write_bytes(root,META+'/transaction.json',canonical(record))
    try:
        for key in sorted(names):write_bytes(root,key,desired.get(key))
        write_bytes(root,META+'/manifest.json',canonical(after))
        write_bytes(root,META+'/rollback.json',canonical(record))
        write_bytes(root,META+'/transaction.json',None)
    except BaseException:
        # Journal stays until explicit rollback. Never silently replay partial work.
        raise
    prune_empty(root,names-set(desired))


def inspect_plan(root,action,source=PACKAGE) -> tuple[dict[str, object], dict[str, object] | None, dict[str, bytes] | None]:
    current=load_manifest(root)
    if journal(root,'transaction.json') is not None:raise Conflict('unfinished transaction; explicit rollback required')
    bad=conflicts(root,current)
    if action=='init' and (current is None or not current['files']) and route_planner.has_unmanaged_dreampia_data_dir(root):
        bad.append('.dreampia')
    if bad:return {'action':action,'applied':False,'conflicts':bad,'changes':[]},current,None
    if action=='init' and current is not None and current['files']:desired=payload(source)
    elif action=='init':desired=payload(source)
    elif current is None or not current['files']:raise InstallError('project not installed')
    elif action=='update':desired=payload(source)
    else:desired={}
    previous=(current or {'files':{}})['files'];changes=[]
    for key in sorted(set(previous)|set(desired)):
        existing=read_bytes(root,key)
        if key not in previous and existing is not None:bad.append(key);continue
        target=desired.get(key)
        if existing!=target:changes.append({'path':key,'operation':'remove' if target is None else 'create' if existing is None else 'replace','before':sha(existing) if existing is not None else None,'after':sha(target) if target is not None else None})
    return {'action':action,'package_version':VERSION,'applied':False,'conflicts':bad,'changes':changes},current,desired


def install(root,action,apply=False,source=PACKAGE) -> dict[str, object]:
    plan,current,desired=inspect_plan(root,action,source)
    if plan['conflicts']:raise Conflict('managed or preexisting file conflict')
    if not apply:return plan
    with locked(root):
        plan,current,desired=inspect_plan(root,action,source)
        if plan['conflicts']:raise Conflict('managed or preexisting file conflict')
        if plan['changes'] or current is None or current['package_version']!=VERSION:
            transaction(root,current,desired,VERSION)
        plan['applied']=True
    return plan


def rollback_plan(root) -> tuple[dict[str, object], dict[str, object]]:
    pending=journal(root,'transaction.json');record=pending or journal(root,'rollback.json')
    if record is None:raise InstallError('no rollback available')
    current=load_manifest(root)
    if (current not in (record['before'],record['after'])) if pending else (current!=record['after']):raise Conflict('rollback manifest changed')
    changes=[]
    for name,row in record['files'].items():
        existing=read_bytes(root,name);before=decode(row['before']);after=decode(row['after'])
        if (existing not in (before,after)) if pending else (existing!=after):raise Conflict('rollback file changed')
        if existing!=before:changes.append({'path':name,'operation':'restore' if before is not None else 'remove'})
    return {'action':'rollback','applied':False,'recovering_partial':pending is not None,'changes':changes},record


def rollback(root,apply=False) -> dict[str, object]:
    plan,record=rollback_plan(root)
    if not apply:return plan
    with locked(root):
        plan,record=rollback_plan(root)
        if not plan['recovering_partial']:
            reverse={'schema_version':1,'before':record['after'],'after':record['before'],
                     'files':{name:{'before':row['after'],'after':row['before']} for name,row in record['files'].items()}}
            write_bytes(root,META+'/transaction.json',canonical(reverse))
        for name,row in record['files'].items():write_bytes(root,name,decode(row['before']))
        write_bytes(root,META+'/manifest.json',None if record['before'] is None else canonical(record['before']))
        write_bytes(root,META+'/transaction.json',None)
        prior=journal(root,'rollback.json')
        if not plan['recovering_partial'] or prior is None or prior['after']!=record['before']:
            write_bytes(root,META+'/rollback.json',None)
        prune_empty(root,record['files']);plan['applied']=True
    return plan



# ---- Level-6 internal workflow commands: project presets, gates, client-safe export ----
USER_PREFIXES=('docs/','data/','evidence/','client/','app/','tests/','web/','.dreampia/generated/','contaminated-zone/','approved-spec/','implementation/')
PROJECT_TYPES=('assessment-service','cleanroom-reconstruct','fullstack-web','api-service')
VERIFY_GATES=('before-dev-start','before-claim-complete','before-client-send','app-static','ui-evidence')


def user_name(name) -> str:
    if not isinstance(name,str) or not name or '\x00' in name or '\\' in name:raise InstallError('invalid user path')
    p=pathlib.PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or p.as_posix()!=name:raise InstallError('path escape')
    if not any(name.startswith(prefix) or name==prefix.rstrip('/') for prefix in USER_PREFIXES):raise InstallError('unsupported generated path')
    return name


def safe_user(root,name) -> pathlib.Path:
    user_name(name);path=root/name
    for p in [path,*path.parents]:
        if p==root.parent:break
        if p.is_symlink():raise InstallError('symlink unsupported')
        if p.exists() and p!=path and not p.is_dir():raise InstallError('parent must be directory')
        if p==root:break
    return path


def read_text_file(path) -> str:
    return pathlib.Path(path).read_text(encoding='utf-8')


def preset_files(kind) -> dict[str, bytes]:
    if kind not in PROJECT_TYPES:raise InstallError('unsupported project type')
    assets=PACKAGE/'ai-dev-execution/assets'
    base_mapping={
        'docs/00_PROJECT_BRIEF.md':assets/'templates/00-project-brief.md',
        'docs/01_PRD_REQUIREMENTS.md':assets/'templates/01-prd.md',
        'docs/02_IA_UX.md':assets/'templates/02-ia-ux.md',
        'docs/03_ARCHITECTURE_TRD.md':assets/'templates/03-trd-architecture.md',
        'docs/04_DATA_API_CONTRACTS.md':assets/'templates/05-contracts-data.md',
        'docs/05_SECURITY_PRIVACY.md':assets/'templates/security-privacy/minor-privacy-checklist.md',
        'docs/06_TEST_PLAN.md':assets/'templates/06-test-plan.md',
        'docs/07_BACKLOG.md':assets/'templates/07-backlog.md',
        'docs/08_RUNBOOK.md':assets/'templates/08-release-runbook.md',
        'docs/09_DECISION_LOG.md':assets/'templates/09-decision-log.md',
        'docs/10_PROGRESS_HANDOFF.md':assets/'templates/10-progress-handoff.md',
        'evidence/README.md':assets/'internal/checklists/before-claim-complete.md',
        '.dreampia/generated/AGENT_ROUTER.md':assets/'internal/pipeline/agent-router.md',
        '.dreampia/generated/LEVEL6_PIPELINE.md':assets/'internal/pipeline/level6-pipeline.md',
    }
    if kind=='assessment-service':
        base_mapping.update({
            'docs/ASSESSMENT_PRD.md':assets/'templates/assessment-service/assessment-prd.md',
            'docs/NO_SIGNUP_STUDENT_FLOW.md':assets/'templates/assessment-service/no-signup-student-flow.md',
            'docs/ADMIN_DASHBOARD_SPEC.md':assets/'templates/assessment-service/admin-dashboard-spec.md',
            'data/question-bank-schema.json':assets/'templates/assessment-service/question-bank-schema.json',
            'data/scoring-rules-schema.json':assets/'templates/assessment-service/scoring-rules-schema.json',
        })
    out={}
    header=f'<!-- generated_by: dreampia scaffold {kind}; review before client delivery -->\n'.encode('utf-8')
    for target,source in base_mapping.items():
        if not source.is_file():raise InstallError('preset source missing')
        content=source.read_bytes()
        if target.startswith('docs/'):
            content=header+content
        out[target]=content
    if kind=='assessment-service':
        out['docs/ASSESSMENT_PRD.md'] += (
            b'\n## Baseline SDD Traceability\n'
            b'- PRD-R001: Student no-signup assessment submission and admin export (UX-S001, API-001, TASK-001, TEST-001) approved\n'
            b'- TASK-001: Implement student submission vertical slice (PRD-R001, TEST-001)\n'
            b'- TEST-001: Verify submission persistence and admin audit log (TASK-001)\n'
        )
    elif kind=='cleanroom-reconstruct':
        out['contaminated-zone/README.md']=(
            b'# Contaminated Zone (Reverse-Engineering & Evidence Extraction)\n\n'
            b'- Place legacy binaries, bundles, or reference sources here.\n'
            b'- Run `dreampia reconstruct-inspect` and `dreampia reconstruct-ledger` against this zone.\n'
            b'- NEVER copy implementation code directly from `contaminated-zone/` into `implementation/`.\n'
        )
        out['approved-spec/00_CLEANROOM_SPEC.md']=(
            b'# Approved Cleanroom Specification\n\n'
            b'- Behavioral obligations derived from `evidence/reconstruction-ledger.json`.\n'
            b'- Verified free of raw legacy code snippets.\n'
        )
        out['implementation/README.md']=(
            b'# Cleanroom Implementation Zone\n\n'
            b'- Implement strictly from `approved-spec/` and verify with `dreampia reconstruct-verify`.\n'
        )
        out['docs/CLEANROOM_GOVERNANCE.md']=header+(
            b'# Cleanroom 3-Zone Governance\n\n'
            b'1. `contaminated-zone/`: Legacy artifact inspection and obligation ledger generation.\n'
            b'2. `approved-spec/`: Clean behavioral specification approved by Spec Gate.\n'
            b'3. `implementation/`: Cleanroom re-implementation verified via `reconstruct-verify`.\n\n'
            b'## Baseline SDD Traceability\n'
            b'- PRD-R001: Cleanroom behavioral parity and zero-contamination verification (API-001, TASK-001, TEST-001) approved\n'
            b'- TASK-001: Reconstruct approved specification obligations (PRD-R001, TEST-001)\n'
            b'- TEST-001: Verify 100% obligation coverage and cleanroom isolation (TASK-001)\n'
        )
    elif kind=='fullstack-web':
        out['docs/WEB_SYSTEM_SPEC.md']=header+(
            b'# Fullstack Web Application Specification\n\n'
            b'## Core Routes & UI Flows\n\n- Primary user flow and responsive viewport budgets.\n\n'
            b'## Baseline SDD Traceability\n'
            b'- PRD-R001: Primary user flow and responsive viewport compliance (UX-S001, API-001, TASK-001, TEST-001) approved\n'
            b'- TASK-001: Implement primary fullstack vertical slice (PRD-R001, TEST-001)\n'
            b'- TEST-001: Verify UI flow and persistence (TASK-001)\n'
        )
        out['app/README.md']=b'# Fullstack Web Application Workspace\n'
    elif kind=='api-service':
        out['docs/API_SERVICE_SPEC.md']=header+(
            b'# API & Backend Service Specification\n\n'
            b'## Endpoints, Schema Contracts & Error Envelopes\n\n- Deterministic JSON contracts and fail-closed validation.\n\n'
            b'## Baseline SDD Traceability\n'
            b'- PRD-R001: Deterministic JSON endpoint contract and error envelope (API-001, TASK-001, TEST-001) approved\n'
            b'- TASK-001: Implement core API endpoint and schema validator (PRD-R001, TEST-001)\n'
            b'- TEST-001: Verify endpoint response schema and status codes (TASK-001)\n'
        )
        out['app/README.md']=b'# API Service Implementation Workspace\n'
    return out


def project_scaffold(root,kind,apply=False) -> dict[str, object]:
    files=preset_files(kind);changes=[];conflicts=[]
    for name,data in sorted(files.items()):
        p=safe_user(root,name)
        if p.exists():conflicts.append(name)
        else:changes.append({'path':name,'operation':'create','after':sha(data)})
    plan={'action':'scaffold','project_type':kind,'applied':False,'conflicts':conflicts,'changes':changes}
    if conflicts or not apply:return plan
    for name,data in sorted(files.items()):write_bytes(root,name,data)
    plan['applied']=True
    return plan


def list_project_files(root,prefix) -> list[pathlib.Path]:
    base=safe_user(root,prefix.rstrip('/')+'/placeholder').parent
    if not base.exists():return []
    files=[]
    for p in sorted(base.rglob('*')):
        safe_user(root,p.relative_to(root).as_posix())
        if p.is_file():
            if not stat.S_ISREG(p.stat().st_mode):raise InstallError('regular file required')
            files.append(p)
        elif not p.is_dir():raise InstallError('special project file unsupported')
    return files


DOMAIN_SPEC_DOCS=(
    'docs/ASSESSMENT_PRD.md',
    'docs/CLEANROOM_GOVERNANCE.md',
    'docs/WEB_SYSTEM_SPEC.md',
    'docs/API_SERVICE_SPEC.md',
)


def verify_gate(root,gate) -> dict[str, object]:
    if gate not in VERIFY_GATES:raise InstallError('unsupported gate')
    checks=[]
    def add(name,ok,detail='') -> None:
        checks.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    d=doctor(root);add('dreampia install healthy',d['healthy'],json.dumps({'package_version':d.get('package_version'),'bundle':d.get('skill_bundle',{}).get('status')},ensure_ascii=False))
    is_self_hosted=bool(d.get('self_hosted'))
    if gate=='before-dev-start':
        if is_self_hosted and not (root/'docs/00_PROJECT_BRIEF.md').is_file():
            add('ARCHITECTURE.ko.md',(root/'ARCHITECTURE.ko.md').is_file())
            add('docs/acceptance-requirements.json',(root/'docs/acceptance-requirements.json').is_file())
            add('ai-dev-execution/SKILL.md',(root/'ai-dev-execution/SKILL.md').is_file())
        else:
            for path in ('docs/00_PROJECT_BRIEF.md','docs/01_PRD_REQUIREMENTS.md'):
                add(path,(root/path).is_file())
            matched_domain=next((p for p in DOMAIN_SPEC_DOCS if (root/p).is_file()),None)
            add(matched_domain or 'docs/ASSESSMENT_PRD.md',matched_domain is not None)
    elif gate=='before-claim-complete':
        ev=list_project_files(root,'evidence/')
        add('evidence files present',bool(ev),str(len(ev)))
        if is_self_hosted and not (root/'docs/10_PROGRESS_HANDOFF.md').is_file():
            add('progress handoff present',(root/'evidence/forward-test/handoff.md').is_file() or (root/'evidence/autopilot-verdict.json').is_file())
            add('app check evidence valid',(root/'evidence/verification.json').is_file() and (root/'evidence/sdd-ledger.json').is_file())
            add('ui check evidence valid',(root/'evidence/autopilot-verdict.json').is_file())
        else:
            add('progress handoff present',(root/'docs/10_PROGRESS_HANDOFF.md').is_file())
            add('app check evidence valid',evidence_valid(root,'app'))
            add('ui check evidence valid',evidence_valid(root,'ui'))
    elif gate=='app-static':
        add('web/package.json',(root/'web/package.json').is_file())
        add('web/app/page.tsx',(root/'web/app/page.tsx').is_file())
        add('web/app/admin/page.tsx',(root/'web/app/admin/page.tsx').is_file())
        add('web/playwright.config.ts',(root/'web/playwright.config.ts').is_file())
        add('web/tests/ui/smoke.spec.ts',(root/'web/tests/ui/smoke.spec.ts').is_file())
        add('web/lib/scoring.ts',(root/'web/lib/scoring.ts').is_file())
        add('web/lib/store.ts',(root/'web/lib/store.ts').is_file())
        add('web/app/admin/export/route.ts',(root/'web/app/admin/export/route.ts').is_file())
    elif gate=='ui-evidence':
        add('ui check evidence valid',evidence_valid(root,'ui'))
    elif gate=='before-client-send':
        client=list_project_files(root,'client/')
        docs=list_project_files(root,'docs/')
        if is_self_hosted and not client:
            leaked=[p.relative_to(root).as_posix() for p in docs if contains_secret(p.read_bytes())]
            add('client output exists',(root/'README.ko.md').is_file() and (root/'README.md').is_file(),'self-hosted-docs')
            add('docs exist for summary',bool(docs),str(len(docs)))
            add('client outputs explicitly approved and secret-free',not leaked,str(len(leaked)))
        else:
            leaked=[p.relative_to(root).as_posix() for p in client if not client_artifact_safe(root,p)]
            add('client output exists',bool(client),str(len(client)))
            add('docs exist for summary',bool(docs),str(len(docs)))
            add('client outputs explicitly approved and secret-free',not leaked,str(len(leaked)))
    return {'action':'verify','gate':gate,'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL','checks':checks}


import re as _re
_EXPORT_FORBIDDEN_PART_RE=_re.compile(r'(?i)(internal|private|secret|credential|agent|prompt|rubric)')
_EXPORT_CTRL_CHAR_RE=_re.compile(r'[\x00-\x1f`\\\\]')
_EXPORT_FORBIDDEN_BODY_RE=_re.compile(r'(?i)internal_only|assets/internal/|\.dreampia/|\.agents/|client_export_allowed[\"\s]*:\s*false')
_EXPORT_KEY_LINE_RE=_re.compile(r'^client_export_allowed\s*:')
_EXPORT_TRUE_LINE_RE=_re.compile(r'client_export_allowed:\s*true\s*')
_CLIENT_SECRET_RE=_re.compile(
    r'(?i)-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----'
    r'|\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|secret|token)\b[\"\s]*[:=]\s*[\"\']?[^\s\"\',}]+'
    r'|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}'
    r'|\bAKIA[0-9A-Z]{16}\b'
    r'|\b(?:gh[pousr]_|github_pat_|sk-(?:proj-)?)[A-Za-z0-9_-]{16,}'
)


def export_path_allowed(name) -> bool:
    p=pathlib.PurePosixPath(name)
    return (not p.is_absolute() and '..' not in p.parts and p.as_posix()==name
            and not any(x.startswith('.') or _EXPORT_FORBIDDEN_PART_RE.search(x) for x in p.parts)
            and p.suffix.lower() in ('.md','.txt','.json') and not _EXPORT_CTRL_CHAR_RE.search(name))


def export_content_allowed(name,data) -> bool:
    """Only explicit boolean approval in metadata, never body/snippet approval."""
    if not export_path_allowed(name):return False
    try:text=data.decode('utf-8')
    except UnicodeError:return False
    if _EXPORT_FORBIDDEN_BODY_RE.search(text):return False
    if name.endswith('.json'):
        try:approved=loads(data).get('client_export_allowed') is True
        except (ValueError,AttributeError):return False
    else:
        lines=text.splitlines()
        if not lines or lines[0]!='---' or '---' not in lines[1:]:return False
        metadata=lines[1:lines.index('---',1)]
        approvals=[line for line in metadata if _EXPORT_KEY_LINE_RE.match(line)]
        approved=len(approvals)==1 and bool(_EXPORT_TRUE_LINE_RE.fullmatch(approvals[0]))
    return approved


def contains_secret(data) -> bool:
    text=data.decode('utf-8',errors='replace')
    return bool(_CLIENT_SECRET_RE.search(text))


def approved_exports(root,prefixes) -> tuple[dict[str, bytes], list[str]]:
    selected={};blocked=[]
    for prefix in prefixes:
        for p in list_project_files(root,prefix):
            rel=p.relative_to(root).as_posix()
            if not export_path_allowed(rel):blocked.append(rel);continue
            data=read_bytes(root,user_name(rel))
            if data is None or not export_content_allowed(rel,data):blocked.append(rel);continue
            if contains_secret(data) or contains_secret(rel.encode()):raise InstallError('secret detected in approved client source')
            selected[rel]=data
    return selected,blocked


def client_artifact_safe(root,p) -> bool:
    import zipfile
    name=p.relative_to(root).as_posix()
    try:
        data=read_bytes(root,user_name(name))
        if p.suffix.lower()!='.zip':return data is not None and export_content_allowed(name,data) and not contains_secret(data)
        if any(x.startswith('.') or x.lower() in ('internal','private') for x in pathlib.PurePosixPath(name).parts):return False
        with zipfile.ZipFile(p) as z:
            members=z.infolist()
            if not members or len(members)>1000 or sum(i.file_size for i in members)>20_000_000:return False
            if len({i.filename for i in members})!=len(members):return False
            for i in members:
                if i.is_dir() or stat.S_ISLNK(i.external_attr>>16) or not export_path_allowed(i.filename):return False
                if not i.filename.startswith(('docs/','client/')):return False
                content=z.read(i)
                if not export_content_allowed(i.filename,content) or contains_secret(content):return False
        return True
    except (ValueError,OSError,RuntimeError,zipfile.BadZipFile):return False


def export_client_summary(root,out='client') -> dict[str, object]:
    if out!='client':raise InstallError('output must be client folder')
    target='client/CLIENT_SAFE_SUMMARY.md';safe_user(root,target)
    docs,blocked=approved_exports(root,('docs/',))
    rows=[f'- `{name}`' for name in sorted(docs)]
    body='---\nclient_export_allowed: true\n---\n# Client-Safe Project Summary\n\n명시적으로 고객 전달이 승인된 문서만 포함합니다. 담당자는 전달 전 범위를 재확인해야 합니다.\n\n## Included source docs\n\n'+('\n'.join(rows) if rows else '- 없음')+'\n\n## Confirmation questions\n\n- 운영 기간과 대상 인원을 확정해야 합니다.\n- 개인정보 수집 범위와 보관/삭제 기준을 확정해야 합니다.\n- 관리자 권한과 CSV 다운로드 가능자를 확정해야 합니다.\n'
    data=body.encode('utf-8');write_bytes(root,target,data)
    return {'action':'export-client-summary','output':target,'included':sorted(docs),'excluded_internal':blocked,'sha256':sha(data)}


APP_TYPES=('next-assessment-app','cleanroom-reconstruct-kit','api-service-starter')


def scaffold_app_files(kind) -> dict[str, bytes]:
    if kind=='next-assessment-app':
        base=PACKAGE/'ai-dev-execution/assets/scaffolds/next-assessment-app'
        if not base.is_dir():raise InstallError('app scaffold source missing')
        out={}
        for p in sorted(base.rglob('*')):
            if p.is_symlink():raise InstallError('scaffold symlink')
            if p.is_file():
                rel=p.relative_to(base).as_posix()
                target='web/'+('.gitignore' if rel=='gitignore.template' else rel)
                out[target]=p.read_bytes()
        return out
    if kind=='cleanroom-reconstruct-kit':
        return {
            'contaminated-zone/reference_contract.py': (
                b'"""Legacy reference module placed in contaminated-zone for surface extraction only."""\n'
                b'def compute_tier_score(raw_points: int, weight: int) -> int:\n'
                b'    return max(0, raw_points * weight)\n'
            ),
            'approved-spec/00_CLEANROOM_SPEC.md': (
                b'# Approved Cleanroom Specification\n\n'
                b'## Required Public Symbols\n\n'
                b'- `compute_tier_score`: Accepts integer points and weight, returning non-negative weighted score.\n'
            ),
            'implementation/reconstructed_service.py': (
                b'"""Cleanroom implementation derived strictly from approved-spec/00_CLEANROOM_SPEC.md."""\n'
                b'def compute_tier_score(points: int, multiplier: int) -> int:\n'
                b'    result = int(points) * int(multiplier)\n'
                b'    return result if result > 0 else 0\n'
            ),
            'tests/test_cleanroom_parity.py': (
                b'import unittest\n'
                b'from implementation.reconstructed_service import compute_tier_score\n\n'
                b'class CleanroomParityTests(unittest.TestCase):\n'
                b'    def test_compute_tier_score(self) -> None:\n'
                b'        self.assertEqual(compute_tier_score(12, 3), 36)\n'
                b'        self.assertEqual(compute_tier_score(-5, 3), 0)\n\n'
                b'if __name__ == "__main__":\n'
                b'    unittest.main()\n'
            ),
        }
    if kind=='api-service-starter':
        return {
            'app/__init__.py': b'',
            'app/service.py': (
                b'"""Deterministic JSON API service core."""\n'
                b'def handle_health() -> dict[str, object]:\n'
                b'    return {"status": "ok", "service": "dreampia-api-starter"}\n'
            ),
            'tests/test_api_service.py': (
                b'import unittest\n'
                b'from app.service import handle_health\n\n'
                b'class ApiServiceTests(unittest.TestCase):\n'
                b'    def test_health_contract(self) -> None:\n'
                b'        res = handle_health()\n'
                b'        self.assertEqual(res["status"], "ok")\n\n'
                b'if __name__ == "__main__":\n'
                b'    unittest.main()\n'
            ),
        }
    raise InstallError('unsupported app scaffold')


def scaffold_app(root,kind,apply=False) -> dict[str, object]:
    files=scaffold_app_files(kind);changes=[];conflicts=[]
    for name,data in sorted(files.items()):
        path=safe_user(root,name)
        if path.exists():conflicts.append(name)
        else:changes.append({'path':name,'operation':'create','after':sha(data)})
    plan={'action':'scaffold-app','app_type':kind,'applied':False,'conflicts':conflicts,'changes':changes}
    if conflicts or not apply:return plan
    for name,data in sorted(files.items()):write_bytes(root,name,data)
    plan['applied']=True
    return plan


def plan_slice(root,slice_name,apply=False) -> dict[str, object]:
    allowed={'student-submit-flow':'assets/templates/assessment-service/vertical-slice-student-submit.md'}
    if slice_name not in allowed:raise InstallError('unsupported slice')
    src=PACKAGE/'ai-dev-execution'/allowed[slice_name]
    if not src.is_file():raise InstallError('slice source missing')
    target=f'.dreampia/generated/slices/{slice_name}.md'
    data=src.read_bytes();path=safe_user(root,target)
    plan={'action':'plan-slice','slice':slice_name,'applied':False,'conflicts':[],'changes':[]}
    if path.exists():plan['conflicts'].append(target);return plan
    plan['changes'].append({'path':target,'operation':'create','after':sha(data)})
    if apply:write_bytes(root,target,data);plan['applied']=True
    return plan



APP_REQUIRED=('web/package.json','web/app/page.tsx','web/app/admin/page.tsx','web/playwright.config.ts','web/tests/ui/smoke.spec.ts','web/lib/scoring.ts')
UI_REQUIRED=('web/package.json','web/playwright.config.ts','web/tests/ui/smoke.spec.ts')
EVIDENCE_MAX_AGE_SECONDS=86400


def source_fingerprint(root) -> str:
    """Content fingerprint; exclude dependencies and generated execution artifacts."""
    web=safe_user(root,'web/package.json').parent
    ignored={'node_modules','.next','test-results','playwright-report','.git','__pycache__'}
    files={}
    if not web.is_dir():raise InstallError('web source missing')
    for base,dirs,names in os.walk(web,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in ignored)
        for d in dirs:
            if (pathlib.Path(base)/d).is_symlink():raise InstallError('source symlink')
        for name in sorted(names):
            p=pathlib.Path(base)/name
            if name in ('next-env.d.ts','tsconfig.tsbuildinfo'):continue
            rel=p.relative_to(root).as_posix()
            data=read_bytes(root,rel)
            if data is not None:files[rel]=sha(data)
    return sha(canonical(files))


def evidence_valid(root,kind) -> bool:
    """Fail closed on missing, malformed, stale, failed or source-mismatched evidence."""
    import datetime
    try:
        e=loads(read_bytes(root,'evidence/'+kind+'-check.json'))
        if e.get('schema_version')!=2 or e.get('status')!='PASS':return False
        stamp=datetime.datetime.fromisoformat(e['generated_at'].replace('Z','+00:00'))
        age=(datetime.datetime.now(datetime.timezone.utc)-stamp).total_seconds()
        if not 0<=age<=EVIDENCE_MAX_AGE_SECONDS or e['source_fingerprint']!=source_fingerprint(root):return False
        checks=e['checks']
        if not isinstance(checks,list) or not checks:return False
        required: set[str]=set(APP_REQUIRED if kind=='app' else UI_REQUIRED)
        required.update(('npm run build','npm run test:unit','unit test script','source unchanged') if kind=='app' else ('npm run test:ui','screenshots','source unchanged'))
        if any(not isinstance(c,dict) or c.get('status')!='PASS' or not isinstance(c.get('name'),str) for c in checks):return False
        names=[c['name'] for c in checks]
        if len(set(names))!=len(names) or not required.issubset(names):return False
        if kind=='ui':
            run=e['run_id']
            if not isinstance(run,str) or not __import__('re').fullmatch('[0-9a-f]{32}',run):return False
            shots=e['screenshots'];hashes=e['screenshot_sha256']
            if not isinstance(shots,list) or not shots or len(set(shots))!=len(shots) or set(hashes)!=set(shots):return False
            for name in shots:
                if not isinstance(name,str) or not name.startswith('evidence/ui/'+run+'/') or not name.endswith('.png'):return False
                data=read_bytes(root,user_name(name))
                if data is None or not data.startswith(b'\x89PNG\r\n\x1a\n') or sha(data)!=hashes[name]:return False
        return True
    except (ValueError,TypeError,KeyError,OSError,AttributeError):return False


def app_check(root,apply=False) -> dict[str, object]:
    checks=[]
    def add(name,status,detail='') -> None:
        checks.append({'name':name,'status':status,'detail':detail})
    for name in APP_REQUIRED:add(name,'PASS' if safe_user(root,name).is_file() else 'FAIL')
    web=root/'web'
    if apply and web.is_dir():
        import subprocess,datetime
        fingerprint=source_fingerprint(root)
        try:
            script=loads(read_bytes(root,'web/package.json'))['scripts']['test:unit']
            valid=isinstance(script,str) and bool(script.strip()) and not __import__('re').search(r'(?i)TODO|placeholder|console\.log|^\s*(echo|true)(\s|$)',script)
        except (ValueError,TypeError,KeyError):valid=False
        add('unit test script','PASS' if valid else 'FAIL','real test:unit required; placeholder scripts are not verification')
        if (web/'node_modules').is_dir():
            for cmd in (['npm','run','build'],['npm','run','test:unit']):
                try:
                    r=subprocess.run(cmd,cwd=str(web),text=True,capture_output=True,timeout=180)
                    add(' '.join(cmd),'PASS' if r.returncode==0 else 'FAIL',(r.stdout+r.stderr)[-2000:])
                except (OSError,subprocess.TimeoutExpired) as e:add(' '.join(cmd),'FAIL',type(e).__name__)
        else:
            add('npm build/test','NOT_RUN','web/node_modules missing; run npm install in web/ before executable app verification')
        add('source unchanged','PASS' if fingerprint==source_fingerprint(root) else 'FAIL')
        evidence={'schema_version':2,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_fingerprint':fingerprint,'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL','checks':checks}
        data=canonical(evidence);write_bytes(root,'evidence/app-check.json',data)
        return {'action':'app-check','applied':True,'evidence':'evidence/app-check.json','status':evidence['status'],'checks':checks}
    return {'action':'app-check','applied':False,'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL','checks':checks}


def ui_check(root,apply=False) -> dict[str, object]:
    checks=[]
    def add(name,status,detail='') -> None:
        checks.append({'name':name,'status':status,'detail':detail})
    web=root/'web';run_id=uuid.uuid4().hex
    evidence_dir=safe_user(root,'evidence/ui/'+run_id+'/placeholder').parent
    for name in UI_REQUIRED:add(name,'PASS' if safe_user(root,name).is_file() else 'FAIL')
    if apply and web.is_dir():
        import subprocess,datetime,os
        fingerprint=source_fingerprint(root)
        if (web/'node_modules').is_dir():
            evidence_dir.mkdir(parents=True,exist_ok=True)
            env=os.environ.copy();env['DREAMPIA_UI_EVIDENCE']=str(evidence_dir)
            try:
                r=subprocess.run(['npm','run','test:ui'],cwd=str(web),text=True,capture_output=True,timeout=240,env=env)
                add('npm run test:ui','PASS' if r.returncode==0 else 'FAIL',(r.stdout+r.stderr)[-2000:])
            except (OSError,subprocess.TimeoutExpired) as e:add('npm run test:ui','FAIL',type(e).__name__)
        else:
            add('npm run test:ui','NOT_RUN','web/node_modules missing; run npm install and playwright install before UI verification')
        screenshots=[];screenshot_hashes={}
        for p in sorted(evidence_dir.rglob('*.png')) if evidence_dir.exists() else []:
            name=p.relative_to(root).as_posix();data=read_bytes(root,user_name(name))
            if data is not None and data.startswith(b'\x89PNG\r\n\x1a\n'):
                screenshots.append(name);screenshot_hashes[name]=sha(data)
        add('screenshots','PASS' if screenshots else 'NOT_RUN',json.dumps(screenshots,ensure_ascii=False))
        add('source unchanged','PASS' if fingerprint==source_fingerprint(root) else 'FAIL')
        evidence={'schema_version':2,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_fingerprint':fingerprint,'run_id':run_id,'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL','checks':checks,'screenshots':screenshots,'screenshot_sha256':screenshot_hashes}
        data=canonical(evidence);write_bytes(root,'evidence/ui-check.json',data)
        return {'action':'ui-check','applied':True,'evidence':'evidence/ui-check.json','status':evidence['status'],'checks':checks,'screenshots':screenshots}
    return {'action':'ui-check','applied':False,'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL','checks':checks}

def package_client(root,out='client-package.zip') -> dict[str, object]:
    import io,re,zipfile
    if not isinstance(out,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*\.zip',out):raise InstallError('output must be simple .zip filename')
    target='client/'+out;safe_user(root,target)
    selected,excluded=approved_exports(root,('client/','docs/'))
    if not selected:raise InstallError('no explicitly approved client files')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for rel,data in sorted(selected.items()):z.writestr(rel,data)
    data=buffer.getvalue();write_bytes(root,target,data)
    return {'action':'package-client','output':target,'included':sorted(selected),'excluded_internal':excluded,'sha256':sha(data)}

def doctor(root) -> dict[str, object]:
    current=load_manifest(root);pending=journal(root,'transaction.json') is not None
    bad=conflicts(root,current);configs={}
    for name,check in [('.dreampia/team.json',validate_policy),('.dreampia/project.json',validate_project)]:
        raw=read_bytes(root,name)
        if raw is not None:check(loads(raw));configs[name]='VALID'
    bundle={'status':'LEGACY_UNDECLARED'}
    if current is None and pathlib.Path(root).resolve()==PACKAGE.resolve():
        for name,origin,check in [('team/policy.json','team/policy.json',validate_policy),('team/project.json','team/project.json',validate_project)]:
            raw=read_bytes(PACKAGE,origin)
            if raw is not None:check(loads(raw));configs[name]='VALID'
        try:
            info=skill_bundle.validate(skill_bundle.read(PACKAGE/'ai-dev-execution'),VERSION)
            bundle={k:info[k] for k in ('name','version','source','manifest_sha256','missing_optional')};bundle['status']='SELF_HOSTED_VALID'
        except (ValueError,UnicodeError):
            bundle={'status':'INVALID'};bad.append('ai-dev-execution/'+skill_bundle.NAME)
        return {'python':'.'.join(map(str,sys.version_info[:3])),'python_supported':sys.version_info>=(3,9),'platform':sys.platform,
                'installed':True,'self_hosted':True,'package_version':VERSION,
                'conflicts':bad,'unfinished_transaction':pending,'configs':configs,'provider_calls':0,'skill_bundle':bundle,
                'healthy':not bad and not pending and sys.version_info>=(3,9)}
    if current and SKILL+skill_bundle.NAME in current['files']:
        bundle={'status':'UNCHECKED_CONFLICT'}
        if not bad:
            try:
                info=skill_bundle.validate(skill_bundle.read(pathlib.Path(root)/SKILL),current['package_version'])
                bundle={k:info[k] for k in ('name','version','source','manifest_sha256','missing_optional')};bundle['status']='VALID'
            except (ValueError,UnicodeError):bundle={'status':'INVALID'};bad.append(SKILL+skill_bundle.NAME)
    return {'python':'.'.join(map(str,sys.version_info[:3])),'python_supported':sys.version_info>=(3,9),'platform':sys.platform,
            'installed':bool(current and current['files']),'package_version':current['package_version'] if current else None,
            'conflicts':bad,'unfinished_transaction':pending,'configs':configs,'provider_calls':0,'skill_bundle':bundle,
            'healthy':bool(current and current['files']) and not bad and not pending and sys.version_info>=(3,9)}


def route_plan_check(root: pathlib.Path, goal: str) -> dict[str, object]:
    decision = route_planner.plan_route(goal, root=root)
    expansion = route_planner.expand_prompt_brief(goal, root=root, decision=decision)
    return {
        'action': 'route-plan',
        'status': 'PASS' if decision.goal_kind != 'unsupported' else 'FAIL',
        **decision.to_dict(),
        'prompt_expansion': expansion.to_dict(),
    }


def expand_prompt_check(root: pathlib.Path, goal: str) -> dict[str, object]:
    decision = route_planner.plan_route(goal, root=root)
    expansion = route_planner.expand_prompt_brief(goal, root=root, decision=decision)
    return {
        'action': 'expand-prompt',
        'status': 'PASS' if decision.goal_kind != 'unsupported' else 'FAIL',
        **expansion.to_dict(),
        'route_decision': decision.to_dict(),
    }


def next_actions_check(root: pathlib.Path, goal: str = '') -> dict[str, object]:
    return route_planner.recommend_next_actions(root=root, goal=goal)



def visual_check(
    root: pathlib.Path,
    manifest_rel: str | None = None,
    baseline_rel: str | None = None,
    candidate_rel: str | None = None,
    max_diff_ratio: float = 0.0,
) -> dict[str, object]:
    if manifest_rel:
        manifest_path = visual_acceptance._safe_relative_path(root, manifest_rel)
        res = visual_acceptance.verify_visual_acceptance(manifest_path, root=root)
        return {'action': 'visual-check', **res}
    if baseline_rel and candidate_rel:
        base_path = visual_acceptance._safe_relative_path(root, baseline_rel)
        cand_path = visual_acceptance._safe_relative_path(root, candidate_rel)
        diff = visual_acceptance.compare_visuals(base_path, cand_path, max_diff_ratio)
        return {'action': 'visual-check', **diff}
    raise InstallError('visual-check requires --manifest or both --baseline and --candidate')


def instruction_check(root: pathlib.Path) -> dict[str, object]:
    res = write_boundary.check_instruction_drift(root)
    return {'action': 'instruction-check', **res}


def router_discover_check(root: pathlib.Path) -> dict[str, object]:
    res = universal_router.discover_harnesses(root)
    return {'action': 'router-discover', 'status': 'PASS', **res}


def router_materialize_check(root: pathlib.Path, harness_target: str, apply: bool) -> dict[str, object]:
    return universal_router.materialize_harness(root, harness_target, source=PACKAGE, apply=apply)


def router_export_plugin_check() -> dict[str, object]:
    res = universal_router.export_router_plugin(PACKAGE)
    return {'action': 'router-export-plugin', 'status': 'PASS', **res}


def router_dispatch_check(
    root: pathlib.Path,
    goal: str,
    harness_target: str,
    previous_response_id: str | None = None,
) -> dict[str, object]:
    req: dict[str, object] = {
        'input': goal,
        'metadata': {'harness_id': harness_target if harness_target != 'all' else 'auto'},
    }
    if previous_response_id:
        req['previous_response_id'] = previous_response_id
    res = universal_router.dispatch_router_task(root, req)
    return {
        **res,
        'action': 'router-dispatch',
        'router_status': res.get('status'),
        'status': 'PASS' if res.get('status') == 'completed' else 'FAIL',
    }


def reconstruct_doctor_check(
    install_tool: str | None = None,
    apply: bool = False,
) -> dict[str, object]:
    res = reconstruct_engine.reconstruct_doctor(install_tool=install_tool, apply=apply)
    return {'action': 'reconstruct-doctor', **res}


def reconstruct_inspect_check(root: pathlib.Path, target_rel: str) -> dict[str, object]:
    if not target_rel:
        raise InstallError('reconstruct-inspect requires --target')
    target_path = safe_user(root, user_name(target_rel))
    info = reconstruct_engine.inspect_artifact(target_path)
    return {'action': 'reconstruct-inspect', 'status': 'PASS', **info}


def reconstruct_ledger_check(root: pathlib.Path, source_rel: str, apply: bool = False) -> dict[str, object]:
    if not source_rel:
        raise InstallError('reconstruct-ledger requires --source')
    ledger = reconstruct_engine.build_obligation_ledger(root, source_rel)
    ledger_rel = 'evidence/reconstruction-ledger.json'
    if apply:
        write_bytes(root, ledger_rel, canonical(ledger))
    return {
        'action': 'reconstruct-ledger',
        'status': 'PASS',
        'applied': apply,
        'ledger_path': ledger_rel if apply else None,
        **ledger,
    }


def reconstruct_verify_check(root: pathlib.Path, ledger_rel: str, candidate_rel: str) -> dict[str, object]:
    eff_ledger_rel = ledger_rel or 'evidence/reconstruction-ledger.json'
    raw_ledger = read_bytes(root, user_name(eff_ledger_rel))
    if raw_ledger is None:
        raise InstallError('reconstruction ledger file missing')
    saved_ledger = loads(raw_ledger)
    ref_rel = str(saved_ledger.get('reference_path') or 'contaminated-zone')
    spec_rel = str(saved_ledger.get('spec_path') or 'approved-spec')
    tgt_rel = candidate_rel or str(saved_ledger.get('target_path') or 'implementation')
    live_ledger = reconstruct_engine.build_obligation_ledger(
        root,
        ref_rel,
        spec_rel=spec_rel,
        target_rel=tgt_rel,
    )
    cov = reconstruct_engine.evaluate_reconstruction_coverage(
        live_ledger,
        root=root,
        require_zero_contamination=True,
    )
    return {'action': 'reconstruct-verify', **cov}


def reconstruct_compare_check(root: pathlib.Path, source_rel: str, candidate_rel: str) -> dict[str, object]:
    if not source_rel or not candidate_rel:
        raise InstallError('reconstruct-compare requires --source and --candidate')
    src_path = safe_user(root, user_name(source_rel))
    cand_path = safe_user(root, user_name(candidate_rel))
    cmp_res = reconstruct_engine.compare_surfaces(src_path, cand_path)
    return {'action': 'reconstruct-compare', **cmp_res}


def sdd_ledger_check(root: pathlib.Path, apply: bool = False) -> dict[str, object]:
    ledger = sdd_engine.build_sdd_ledger(root)
    ledger_rel = sdd_engine.DEFAULT_SDD_LEDGER_REL
    if apply:
        write_bytes(root, ledger_rel, canonical(ledger))
    return {
        'action': 'sdd-ledger',
        'status': 'PASS',
        'applied': apply,
        'ledger_path': ledger_rel if apply else None,
        **ledger,
    }


def sdd_verify_check(
    root: pathlib.Path,
    ledger_rel: str | None = None,
    require_tdd_files: bool = True,
) -> dict[str, object]:
    eff_rel = ledger_rel or sdd_engine.DEFAULT_SDD_LEDGER_REL
    saved_ledger: dict[str, object] | None = None
    try:
        raw = read_bytes(root, user_name(eff_rel))
        if raw is not None:
            saved_ledger = loads(raw)
    except InstallError:
        saved_ledger = None
    res = sdd_engine.verify_sdd_compliance(
        root,
        saved_ledger=saved_ledger,
        require_tdd_files=require_tdd_files,
    )
    return {'action': 'sdd-check', **res}


def audit_code_check(
    root: pathlib.Path,
    *,
    check_ui_rules: bool | None = None,
    apply: bool = False,
) -> dict[str, object]:
    res = autopilot_engine.audit_project_code(root, check_ui_rules=check_ui_rules, apply=apply)
    return {'action': 'audit-code', **res}


def context_pack_check(root: pathlib.Path, goal: str = '', apply: bool = False) -> dict[str, object]:
    return autopilot_engine.compile_context_pack(root, goal, apply=apply)


def golden_io_check(root: pathlib.Path, golden_rel: str | None = None) -> dict[str, object]:
    eff_rel = golden_rel or autopilot_engine.DEFAULT_GOLDEN_IO_REL
    res = autopilot_engine.verify_golden_io(root, eff_rel)
    return {'action': 'golden-io', **res}


def autopilot_gate_check(
    root: pathlib.Path,
    goal: str = '',
    allow_doc_only: bool = False,
    apply: bool = False,
) -> dict[str, object]:
    return autopilot_engine.run_autopilot_gate(
        root,
        goal,
        allow_doc_only=allow_doc_only,
        apply=apply,
    )


def blast_radius_check(
    root: pathlib.Path,
    target_rel: str = '',
    apply: bool = False,
) -> dict[str, object]:
    targets = [t.strip() for t in target_rel.split(',') if t.strip()] if target_rel else []
    return autopilot_engine.analyze_blast_radius(
        root,
        target_files=targets,
        apply=apply,
    )


def metric_climb_check(
    root: pathlib.Path,
    benchmark_cmd_str: str,
    metric_regex: str = r'metric:\s*([0-9]+(?:\.[0-9]+)?)',
    direction: str = 'minimize',
    target_rel: str = '',
    immutable_rel: str = '',
    trials: int = 3,
    confidence: float = 0.90,
    hypothesis: str = 'candidate-experiment',
    apply: bool = False,
) -> dict[str, object]:
    import shlex
    if not benchmark_cmd_str.strip():
        raise InstallError('metric-climb requires --cmd')
    cmd_parts = [tok.strip('"\'') for tok in shlex.split(benchmark_cmd_str, posix=(os.name != 'nt'))]
    targets = [t.strip() for t in target_rel.split(',') if t.strip()] if target_rel else []
    immutables = [i.strip() for i in immutable_rel.split(',') if i.strip()] if immutable_rel else []
    return autopilot_engine.run_metric_climb(
        root,
        benchmark_cmd=cmd_parts,
        metric_regex=metric_regex,
        direction=direction,
        target_files=targets,
        immutable_files=immutables,
        trials=trials,
        confidence_threshold=confidence,
        hypothesis=hypothesis,
        apply=apply,
    )


def learn_rule_check(
    root: pathlib.Path,
    rule_ko: str,
    forbidden_regex: str = '',
    severity: str = 'HIGH',
    apply: bool = False,
) -> dict[str, object]:
    return autopilot_engine.learn_project_rule(
        root,
        rule_ko,
        forbidden_regex=forbidden_regex,
        severity=severity,
        apply=apply,
    )


def interview_compile_check(
    root: pathlib.Path,
    goal: str,
    answers: str = '',
    apply: bool = False,
) -> dict[str, object]:
    return sdd_engine.compile_interview_to_sdd(
        root,
        goal,
        answers=answers,
        apply=apply,
    )


def reconstruct_spec_check(
    root: pathlib.Path,
    source_rel: str = 'contaminated-zone',
    apply: bool = False,
) -> dict[str, object]:
    return reconstruct_engine.generate_cleanroom_spec(
        root,
        reference_rel=source_rel or 'contaminated-zone',
        apply=apply,
    )


def squad_worktree_check(
    root: pathlib.Path,
    goal: str = '',
    mode: str = 'plan',
    apply: bool = False,
) -> dict[str, object]:
    return universal_router.plan_or_manage_squad_worktrees(
        root,
        goal=goal,
        mode=mode,
        apply=apply,
    )


_GLOBAL_SKILL_REL_TARGETS: tuple[str, ...] = (
    '.gemini/config/skills/ai-dev-execution',
    '.gemini/antigravity/skills/ai-dev-execution',
    '.claude/skills/ai-dev-execution',
    '.cursor/skills/ai-dev-execution',
    '.agents/skills/ai-dev-execution',
)


def setup_global(
    apply: bool = False,
    home_dir: pathlib.Path | None = None,
    project_dir: pathlib.Path | None = None,
) -> dict[str, object]:
    """원클릭 전역 스킬(Antigravity, Gemini, Claude, Cursor, Agents) 및 MCP 서버 일괄 설치기 (비관리 기존 스킬 자동 백업 지원)."""
    import shutil
    home = (home_dir or pathlib.Path.home()).resolve()
    skill_src = PACKAGE / 'ai-dev-execution'
    if not skill_src.is_dir():
        raise InstallError('skill source directory missing')

    installed_targets: list[str] = []
    backed_up_targets: list[str] = []
    for rel in _GLOBAL_SKILL_REL_TARGETS:
        dst = home / rel
        installed_targets.append(str(dst))
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_dir() and not dst.is_symlink():
                existing_skill = dst / 'SKILL.md'
                if existing_skill.is_file():
                    existing_text = existing_skill.read_text(encoding='utf-8', errors='ignore')
                    if 'Dreampia' not in existing_text:
                        bak = dst.with_name(dst.name + '.pre-dreampia.bak')
                        if not bak.exists():
                            shutil.copytree(dst, bak)
                            backed_up_targets.append(str(bak))
            shutil.copytree(skill_src, dst, dirs_exist_ok=True)

    mcp_cfg_path = home / '.gemini/antigravity/mcp_config.json'
    mcp_project = str(project_dir.resolve()) if project_dir is not None else str(PACKAGE.resolve())
    mcp_entry = {
        'command': sys.executable,
        'args': [
            str((PACKAGE / 'harness/team_cli.py').resolve()),
            'mcp-serve',
            '--project',
            mcp_project,
        ],
    }
    if apply:
        mcp_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        existing_cfg: dict[str, object] = {}
        if mcp_cfg_path.is_file():
            try:
                loaded = json.loads(mcp_cfg_path.read_text(encoding='utf-8'))
                if isinstance(loaded, dict):
                    existing_cfg = loaded
            except ValueError:
                existing_cfg = {}
        servers = existing_cfg.get('mcpServers')
        if not isinstance(servers, dict):
            servers = {}
            existing_cfg['mcpServers'] = servers
        servers['dreampia-skill'] = mcp_entry
        mcp_cfg_path.write_text(json.dumps(existing_cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    project_result: dict[str, object] | None = None
    if project_dir is not None:
        is_self_hosted = project_dir.resolve() == PACKAGE.resolve()
        init_res = {'applied': False, 'self_hosted': True} if is_self_hosted else install(project_dir, 'init', apply)
        mat_res = router_materialize_check(project_dir, 'all', apply)
        project_result = {
            'project': str(project_dir),
            'self_hosted': is_self_hosted,
            'init_applied': init_res.get('applied', False),
            'materialize_applied': mat_res.get('applied', False),
        }

    return {
        'action': 'setup',
        'status': 'PASS',
        'applied': apply,
        'version': VERSION,
        'global_skill_targets': installed_targets,
        'backed_up_targets': backed_up_targets,
        'mcp_config_path': str(mcp_cfg_path),
        'project_setup': project_result,
        'message_ko': (
            f'Dreampia v{VERSION} 전역 스킬({len(installed_targets)}개 호스트 경로) 및 MCP 서버 등록이 완료되었습니다.'
            if apply
            else f'Dreampia v{VERSION} 전역 설치 미리보기입니다. 실제 설치하려면 --apply 옵션을 추가하십시오.'
        ),
    }


def uninstall_global(
    apply: bool = False,
    home_dir: pathlib.Path | None = None,
) -> dict[str, object]:
    """전역 설치된 5개 호스트 스킬 폴더 및 MCP 서버 설정을 안전하게 제거하고 백업본(.pre-dreampia.bak)이 있으면 복원한다."""
    import shutil
    home = (home_dir or pathlib.Path.home()).resolve()
    removed_targets: list[str] = []
    restored_backups: list[str] = []

    for rel in _GLOBAL_SKILL_REL_TARGETS:
        dst = home / rel
        bak = dst.with_name(dst.name + '.pre-dreampia.bak')
        if dst.exists() or bak.exists():
            removed_targets.append(str(dst))
            if apply:
                if dst.exists() and not dst.is_symlink():
                    shutil.rmtree(dst, ignore_errors=True)
                if bak.exists() and not bak.is_symlink():
                    shutil.move(str(bak), str(dst))
                    restored_backups.append(str(dst))

    mcp_cfg_path = home / '.gemini/antigravity/mcp_config.json'
    mcp_removed = False
    if mcp_cfg_path.is_file():
        try:
            loaded = json.loads(mcp_cfg_path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict) and isinstance(loaded.get('mcpServers'), dict):
                servers = loaded['mcpServers']
                if 'dreampia-skill' in servers:
                    mcp_removed = True
                    if apply:
                        del servers['dreampia-skill']
                        mcp_cfg_path.write_text(json.dumps(loaded, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except ValueError:
            pass

    return {
        'action': 'uninstall-global',
        'status': 'PASS',
        'applied': apply,
        'removed_skill_targets': removed_targets,
        'restored_backups': restored_backups,
        'mcp_config_updated': mcp_removed,
        'message_ko': (
            f'Dreampia 전역 스킬({len(removed_targets)}개 경로) 및 MCP 서버 등록이 안전하게 제거되었습니다.'
            if apply
            else f'[미리보기] Dreampia 전역 스킬({len(removed_targets)}개 경로) 제거 계획입니다. 실제 제거하려면 --apply 옵션을 추가하십시오.'
        ),
    }


MUTATING_INSTALL_ACTIONS = (
    'init',
    'update',
    'uninstall',
    'rollback',
    'scaffold',
    'scaffold-app',
    'plan-slice',
)


def project_root(value, allow_package: bool = False, allow_home: bool = False) -> pathlib.Path:
    supplied=pathlib.Path(value).absolute()
    if supplied.is_symlink():raise InstallError('project symlink')
    root=supplied.resolve()
    forbidden = [pathlib.Path('/'), pathlib.Path('/').resolve(), pathlib.Path(root.anchor)]
    if not allow_home:
        forbidden.append(pathlib.Path.home())
    if not allow_package:
        forbidden.append(PACKAGE)
    if not root.is_dir() or root in forbidden:raise InstallError('explicit project directory required')
    return root


def main(argv=None) -> int:
    args=list(sys.argv[1:] if argv is None else argv)
    if args and args[0]=='harness':
        try:from .cli import main as harness_main
        except ImportError:from cli import main as harness_main
        return harness_main(args[1:])
    if args and args[0]=='router':
        return universal_router.main(args[1:])
    if args and args[0]=='mcp':
        try:from .mcp_server import main as mcp_main
        except ImportError:from mcp_server import main as mcp_main
        return mcp_main(args[1:])
    p=argparse.ArgumentParser(description='dreampia: offline project install and internal workflow helper, Python >=3.9 cross-platform')
    p.add_argument('--version',action='version',version=VERSION)
    p.add_argument('action',choices=('setup','install-global','uninstall-global','init','doctor','update','uninstall','rollback','scaffold','verify','export-client-summary','scaffold-app','plan-slice','package-client','app-check','ui-check','route-plan','expand-prompt','next-actions','interview-compile','learn-rule','visual-check','instruction-check','router-discover','router-materialize','router-export-plugin','router-dispatch','squad-worktree','reconstruct-doctor','reconstruct-inspect','reconstruct-ledger','reconstruct-spec','reconstruct-verify','reconstruct-compare','sdd-ledger','sdd-check','spec-check','audit-code','context-pack','golden-io','autopilot-gate','blast-radius','metric-climb','mcp-serve'))
    p.add_argument('--project',default=None);p.add_argument('--apply',action='store_true',help='explicitly execute previewed project changes')
    p.add_argument('--type',choices=PROJECT_TYPES,default='assessment-service',help='project preset for scaffold')
    p.add_argument('--gate',choices=VERIFY_GATES,default='before-dev-start',help='verification gate')
    p.add_argument('--out',default='client',help='project-relative output folder or zip filename for export/package')
    p.add_argument('--app',choices=APP_TYPES,default='next-assessment-app',help='app scaffold preset')
    p.add_argument('--slice',choices=('student-submit-flow',),default='student-submit-flow',help='vertical slice task preset')
    p.add_argument('--goal',default='',help='natural-language goal (Korean/English) for route-plan, expand-prompt, next-actions, interview-compile, learn-rule, squad-worktree, or router-dispatch')
    p.add_argument('--answers',default='',help='semicolon-separated answers to Oracle clarifying questions for interview-compile')
    p.add_argument('--rule',default='',help='Korean project rule text for learn-rule')
    p.add_argument('--forbidden-regex',default='',help='optional regex pattern to block in audit-code for learn-rule')
    p.add_argument('--severity',default='HIGH',help='severity level (CRITICAL, HIGH, MEDIUM, LOW) for learn-rule')
    p.add_argument('--mode','--action',dest='mode',default='plan',help='worktree mode (plan, create, cleanup) for squad-worktree')
    p.add_argument('--no-ui-rules',action='store_true',help='disable default bg-transparent and lucide-react UI rules during audit-code')
    p.add_argument('--manifest',default=None,help='project-relative visual acceptance manifest path')
    p.add_argument('--baseline',default=None,help='project-relative baseline PNG path for visual-check')
    p.add_argument('--candidate',default=None,help='project-relative candidate path for visual-check or reconstruct-verify/compare')
    p.add_argument('--target',default=None,help='project-relative artifact or directory path for reconstruct-inspect or blast-radius/metric-climb')
    p.add_argument('--source',default=None,help='project-relative source artifact or directory path for reconstruct-ledger/spec/compare')
    p.add_argument('--ledger',default=None,help='project-relative ledger path for reconstruct-verify, sdd-check, or golden-io')
    p.add_argument('--cmd',default='',help='benchmark command string for metric-climb')
    p.add_argument('--metric-regex',default=r'metric:\s*([0-9]+(?:\.[0-9]+)?)',help='regex capturing numeric metric for metric-climb')
    p.add_argument('--direction',choices=('minimize','maximize'),default='minimize',help='metric optimization direction for metric-climb')
    p.add_argument('--immutable',default='',help='comma-separated read-only files guarded during metric-climb')
    p.add_argument('--trials',type=int,default=3,help='number of trials for metric-climb')
    p.add_argument('--confidence',type=float,default=0.90,help='Monte Carlo win probability threshold for metric-climb')
    p.add_argument('--allow-doc-only',action='store_true',help='skip executable TDD test file requirement during doc-only SDD check')
    p.add_argument('--max-diff-ratio',type=float,default=0.0,help='max changed pixel ratio for visual-check')
    p.add_argument('--harness',default='all',help='target harness base for router-materialize or router-dispatch')
    p.add_argument('--previous-response-id',default=None,help='previous router response id for session continuation')
    p.add_argument('--install-tool',default=None,help='Tier 2 RE tool id (rizin, jadx, ghidra, wasm2wat, objdump, nm, adb, or all) for reconstruct-doctor')
    a=p.parse_args(args)
    try:
        if a.action in ('setup','install-global'):
            proj_root=project_root(a.project,allow_package=True) if a.project else None
            out=setup_global(apply=a.apply,project_dir=proj_root)
            print(json.dumps(out,ensure_ascii=False,indent=2))
            return 0
        if a.action=='uninstall-global':
            out=uninstall_global(apply=a.apply)
            print(json.dumps(out,ensure_ascii=False,indent=2))
            return 0
        if a.action=='reconstruct-doctor':
            out=reconstruct_doctor_check(install_tool=a.install_tool or a.target,apply=a.apply)
            print(json.dumps(out,ensure_ascii=False,indent=2))
            return 0 if out.get('status')=='PASS' else 1
        if not a.project:
            raise InstallError('explicit project directory required')
        allow_pkg = a.action not in MUTATING_INSTALL_ACTIONS
        allow_hm = a.action == 'mcp-serve'
        root=project_root(a.project,allow_package=allow_pkg,allow_home=allow_hm)
        if a.action=='mcp-serve':
            try:from . import mcp_server
            except ImportError:import mcp_server  # type: ignore[no-redef]
            return mcp_server.serve_stdio(root)
        if a.action=='doctor':out=doctor(root)
        elif a.action=='rollback':out=rollback(root,a.apply)
        elif a.action=='scaffold':out=project_scaffold(root,a.type,a.apply)
        elif a.action=='verify':out=verify_gate(root,a.gate)
        elif a.action=='export-client-summary':out=export_client_summary(root,a.out)
        elif a.action=='scaffold-app':out=scaffold_app(root,a.app,a.apply)
        elif a.action=='plan-slice':out=plan_slice(root,a.slice,a.apply)
        elif a.action=='package-client':out=package_client(root,a.out)
        elif a.action=='app-check':out=app_check(root,a.apply)
        elif a.action=='ui-check':out=ui_check(root,a.apply)
        elif a.action=='route-plan':out=route_plan_check(root,a.goal)
        elif a.action=='expand-prompt':out=expand_prompt_check(root,a.goal)
        elif a.action=='next-actions':out=next_actions_check(root,a.goal)
        elif a.action=='interview-compile':out=interview_compile_check(root,a.goal,a.answers,a.apply)
        elif a.action=='learn-rule':out=learn_rule_check(root,a.rule or a.goal,a.forbidden_regex,a.severity,a.apply)
        elif a.action=='visual-check':out=visual_check(root,a.manifest,a.baseline,a.candidate,a.max_diff_ratio)
        elif a.action=='instruction-check':out=instruction_check(root)
        elif a.action=='router-discover':out=router_discover_check(root)
        elif a.action=='router-materialize':out=router_materialize_check(root,a.harness,a.apply)
        elif a.action=='router-export-plugin':out=router_export_plugin_check()
        elif a.action=='router-dispatch':out=router_dispatch_check(root,a.goal,a.harness,a.previous_response_id)
        elif a.action=='squad-worktree':out=squad_worktree_check(root,a.goal,a.mode,a.apply)
        elif a.action=='reconstruct-inspect':out=reconstruct_inspect_check(root,a.target or '')
        elif a.action=='reconstruct-ledger':out=reconstruct_ledger_check(root,a.source or '',a.apply)
        elif a.action=='reconstruct-spec':out=reconstruct_spec_check(root,a.source or 'contaminated-zone',a.apply)
        elif a.action=='reconstruct-verify':out=reconstruct_verify_check(root,a.ledger or 'evidence/reconstruction-ledger.json',a.candidate or '')
        elif a.action=='reconstruct-compare':out=reconstruct_compare_check(root,a.source or '',a.candidate or '')
        elif a.action=='sdd-ledger':out=sdd_ledger_check(root,a.apply)
        elif a.action in ('sdd-check','spec-check'):out=sdd_verify_check(root,a.ledger,not a.allow_doc_only)
        elif a.action=='audit-code':out=audit_code_check(root,check_ui_rules=(False if a.no_ui_rules else None),apply=a.apply)
        elif a.action=='context-pack':out=context_pack_check(root,a.goal,a.apply)
        elif a.action=='golden-io':out=golden_io_check(root,a.ledger)
        elif a.action=='autopilot-gate':out=autopilot_gate_check(root,a.goal,a.allow_doc_only,a.apply)
        elif a.action=='blast-radius':out=blast_radius_check(root,a.target or '',a.apply)
        elif a.action=='metric-climb':out=metric_climb_check(root,a.cmd,a.metric_regex,a.direction,a.target or '',a.immutable,a.trials,a.confidence,a.goal or 'candidate-experiment',a.apply)
        else:out=install(root,a.action,a.apply)
        print(json.dumps(out,ensure_ascii=False,indent=2))
        return 0 if a.action not in ('doctor','verify','app-check','ui-check','route-plan','expand-prompt','next-actions','interview-compile','learn-rule','visual-check','instruction-check','router-dispatch','squad-worktree','reconstruct-inspect','reconstruct-ledger','reconstruct-spec','reconstruct-verify','reconstruct-compare','sdd-ledger','sdd-check','spec-check','audit-code','context-pack','golden-io','autopilot-gate','blast-radius','metric-climb') or out.get('healthy') or out.get('status')=='PASS' else 1
    except (ValueError,TypeError,KeyError,OSError,RuntimeError) as e:
        print(json.dumps({'error':{'code':getattr(e,'code','INSTALL_INPUT_INVALID'),'type':type(e).__name__}},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())

