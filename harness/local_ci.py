"""Offline local CI. All execution uses test adapters, never provider inference."""
import hashlib,json,os,pathlib,signal,sys,tempfile
try:
    from . import process,package_team
except ImportError:
    import process,package_team
ROOT=pathlib.Path(__file__).resolve().parents[1]
def source_digest() -> str:
    # This tool's explicit source roots only; runtime evidence is not source.
    h=hashlib.sha256()
    for p in package_team.source_files():
        rel=p.relative_to(ROOT).as_posix()
        if rel.startswith('evidence/'):continue
        h.update(rel.encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

def run_checks(commands,env,timeout=180,stopped=lambda:False) -> list[dict[str, object]]:
    results=[];halted=False
    for cmd,cwd in commands:
        if halted or stopped():
            result={'reason':'NOT_RUN','exit_code':None,'stdout':b'','stderr':b''}
        else:
            try:result=process.capture(cmd,env,timeout,stopped=stopped,cwd=cwd)
            except OSError:result={'reason':'NOT_RUN','exit_code':None,'stdout':b'','stderr':b''}
        status=result['reason'] or ('PASS' if result['exit_code']==0 else 'FAIL')
        row={'command':cmd,'cwd':str(cwd),'result':status,'exit':result['exit_code'],'timeout_seconds':timeout}
        print(json.dumps(row));print(result['stdout'].decode('utf8',errors='replace'),end='');print(result['stderr'].decode('utf8',errors='replace'),end='',file=sys.stderr)
        results.append(row)
        if status in ('TIMEOUT','CANCELLED','OUTPUT_LIMIT'):halted=True
    return results

def main() -> int:
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1'};before=source_digest();interrupted=[False];previous={}
    commands=[([sys.executable,'-m','unittest','discover','-s','harness/tests','-v'],ROOT),
              ([sys.executable,'harness/validate_assets.py','ai-dev-execution'],ROOT)]
    with tempfile.TemporaryDirectory(prefix='harness-ci-') as tmp:
        stage=pathlib.Path(tmp)
        import shutil,zipfile
        example=stage/'slots';shutil.copytree(ROOT/'harness/examples/slots',example,ignore=shutil.ignore_patterns('.harness','__pycache__'))
        commands += [([sys.executable,str(ROOT/'harness/cli.py'),'run',str(example)],ROOT),
                     ([sys.executable,str(ROOT/'harness/cli.py'),'trace',str(example)],ROOT),
                     ([sys.executable,'-m','unittest','discover','-s','.', '-v'],example),
                     ([sys.executable,'harness/build.py',str(stage/'harness-0.6.2.pyz')],ROOT),
                     ([sys.executable,str(stage/'harness-0.6.2.pyz'),'--version'],ROOT),
                     ([sys.executable,'harness/eval_runner.py','prepare','evals/suite.json',str(stage/'evaluation')],ROOT),
                     ([sys.executable,'harness/eval_runner.py','aggregate','evals/suite.json',str(stage/'evaluation/results.json')],ROOT)]
        try:
            for sig in (signal.SIGINT,signal.SIGTERM):
                previous[sig]=signal.signal(sig,lambda *_:interrupted.__setitem__(0,True))
            results=run_checks(commands,env,stopped=lambda:interrupted[0])
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)
    after=source_digest();current=before==after
    passed=current and bool(results) and all(x['result']=='PASS' for x in results)
    print(json.dumps({'all_pass':passed,'source_before':before,'source_after':after,'source_current':current,'status':'PASS' if passed else 'STALE' if not current else 'FAIL','provider_inference':'NOT_RUN','remote_ci':'NOT_RUN'}))
    return 0 if passed else 1
if __name__=='__main__':sys.exit(main())
