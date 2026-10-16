"""Isolated local npm install smoke; no network, hooks or global installation."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
def main(argv=None) -> int:
    package=pathlib.Path((argv or sys.argv[1:])[0]).resolve();results=[]
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','DREAMPIA_PYTHON':sys.executable}
    with tempfile.TemporaryDirectory(prefix='dreampia-npm-smoke-') as tmp:
        base=pathlib.Path(tmp);prefix=base/'tools';project=base/'project';project.mkdir();cache=base/'cache'
        (project/'AGENTS.md').write_text('USER CONFIG KEEP');(project/'.env').write_text('FAKE_SECRET_EXCLUDED')
        def run(args,expected=0) -> subprocess.CompletedProcess[str]:
            p=subprocess.run([str(x) for x in args],cwd=base,env=env,capture_output=True,text=True,timeout=60)
            results.append({'argv':[str(x) for x in args],'exit':p.returncode,'expected':expected,'stdout':p.stdout,'stderr':p.stderr})
            if p.returncode!=expected:raise RuntimeError('smoke command failed')
            return p
        run(['npm','install','--offline','--prefix',prefix,'--ignore-scripts','--no-audit','--no-fund','--cache',cache,package])
        exe=prefix/'node_modules/.bin/dreampia'
        run([exe,'--version'])
        run([exe,'init','--project',project]);assert not (project/'.dreampia').exists()
        run([exe,'init','--project',project,'--apply']);run([exe,'doctor','--project',project]);run([exe,'init','--project',project,'--apply'])
        # Re-installing the tarball does not auto-run project configuration.
        run(['npm','install','--offline','--prefix',prefix,'--ignore-scripts','--no-audit','--no-fund','--cache',cache,package])
        run([exe,'update','--project',project]);run([exe,'update','--project',project,'--apply'])
        managed=project/'.dreampia/WORK_CONTRACT.ko.md';old=managed.read_bytes();managed.write_text('USER CHANGE')
        run([exe,'update','--project',project,'--apply'],2);run([exe,'uninstall','--project',project,'--apply'],2);assert managed.read_text()=='USER CHANGE';managed.write_bytes(old)
        run([exe,'uninstall','--project',project]);run([exe,'uninstall','--project',project,'--apply']);assert not managed.exists()
        run([exe,'rollback','--project',project]);run([exe,'rollback','--project',project,'--apply']);run([exe,'doctor','--project',project])
        example=base/'example';__import__('shutil').copytree(ROOT/'harness/examples/slots',example,ignore=__import__('shutil').ignore_patterns('.harness','__pycache__'))
        run([exe,'harness','validate',example]);run([exe,'harness','run',example]);run([exe,'harness','trace',example])
        assert (project/'AGENTS.md').read_text()=='USER CONFIG KEEP' and (project/'.env').read_text()=='FAKE_SECRET_EXCLUDED'
        logs=''.join(p.read_text() for p in (project/'.dreampia-install').rglob('*') if p.is_file());assert 'FAKE_SECRET_EXCLUDED' not in logs
    print(json.dumps({'status':'PASS','commands':results,'registry_access':False,'hooks':False,'global_install':False},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
