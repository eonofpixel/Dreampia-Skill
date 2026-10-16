"""Package only this tool's explicit source roots; never scan a consumer project."""
import argparse
import hashlib
import json
import pathlib
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
DIRECTORIES=('harness','ai-dev-execution','team','adapters','evals','docs','evidence','.github','.claude-plugin','.cursor-plugin')
FILES=('.gitignore','AGENTS.md','VERSION','LICENSE','NOTICE','package.json','pyproject.toml','plugin.json','gemini-extension.json','README.md','README.ko.md','README.ja.md','README.zh-CN.md','ARCHITECTURE.ko.md','CHANGELOG.md','NOTICE.private.md','SUPPORT.ko.md','VERIFICATION.ko.md')
EXCLUDED={'.git','.harness','__pycache__','.env','node_modules','.dreampia-install','.dreampia','.next','test-results','playwright-report','.dreampia-workflow','.workflow','.local-data'}
def source_files(skill_only=False) -> list[pathlib.Path]:
    candidates=[]
    if not skill_only:
        candidates=[ROOT/p for p in FILES]+[ROOT/'bin/dreampia.cjs']
    for directory in (('ai-dev-execution',) if skill_only else DIRECTORIES):
        candidates+=list((ROOT/directory).rglob('*'))
    result=[]
    for p in candidates:
        relative=p.relative_to(ROOT)
        if any(x in EXCLUDED or x.startswith('.env.') or x in ('id_rsa','id_ed25519') or x.endswith(('.pem','.key','.p12')) for x in relative.parts):continue
        if p.is_symlink():raise ValueError('source symlink')
        if p.is_file():result.append(p)
        elif not p.is_dir():raise ValueError('source missing or special file')
    return sorted(set(result))

def build(destination,skill_only=False) -> dict[str, object]:
    dest=pathlib.Path(destination).resolve();dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for p in source_files(skill_only):
            name=p.relative_to(ROOT).as_posix()
            if not skill_only:name='dreampia-skill/'+name
            z.write(p,name)
    with zipfile.ZipFile(dest) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for info in z.infolist():
            rel=pathlib.PurePosixPath(info.filename)
            p=ROOT.joinpath(*(rel.parts if skill_only else rel.parts[1:]))
            if p.read_bytes()!=z.read(info):raise ValueError('ZIP source mismatch')
    return {'path':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'files':len(source_files(skill_only)),'crc':'PASS','source_bytes':'PASS'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination');p.add_argument('--skill-only',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.destination,a.skill_only),indent=2))
