"""Build/install a stdlib zipapp; no network, pip or environment mutation."""
import argparse,json,pathlib,shutil,tempfile,zipapp,hashlib
VERSION='1.1.0'
def build(destination) -> dict[str, str]:
    src=pathlib.Path(__file__).resolve().parent;out=pathlib.Path(destination).resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise ValueError('destination exists; use a new version path')
    with tempfile.TemporaryDirectory() as tmp:
        stage=pathlib.Path(tmp);package=stage/'harness';package.mkdir()
        for p in src.glob('*.py'):shutil.copyfile(p,package/p.name)
        (stage/'__main__.py').write_text('from harness.cli import main\nraise SystemExit(main())\n')
        zipapp.create_archive(stage,out,interpreter='/usr/bin/env python3',compressed=True)
    return {'version':VERSION,'path':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
if __name__=='__main__':
    p=argparse.ArgumentParser(description='Build a versioned local zipapp without installation dependencies')
    p.add_argument('destination');a=p.parse_args()
    print(json.dumps(build(a.destination),indent=2))
