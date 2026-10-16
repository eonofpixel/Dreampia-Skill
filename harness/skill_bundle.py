"""Private bundle byte inventory; not publisher authentication or a skill runtime."""
import hashlib,json,pathlib,re
try:
    from .schema import loads
except ImportError:
    from schema import loads

NAME='bundle-manifest.json'
def sha(data) -> str:return hashlib.sha256(data).hexdigest()
def exact(value,keys) -> None:
    if not isinstance(value,dict) or set(value)!=set(keys):raise ValueError('invalid bundle fields')
def path(value) -> str:
    if not isinstance(value,str) or not value or '\\' in value or '\x00' in value:raise ValueError('invalid bundle path')
    p=pathlib.PurePosixPath(value)
    if p.is_absolute() or p.as_posix()!=value or any(x in ('','.', '..') or x.startswith('.') for x in p.parts):raise ValueError('invalid bundle path')
    if value!='SKILL.md' and p.parts[0] not in ('agents','references','assets'):raise ValueError('unregistered bundle root')
    if any(x.endswith(('.pem','.key','.p12')) for x in p.parts):raise ValueError('private material forbidden')
    return value
def validate(files,version=None) -> dict[str, object]:
    if NAME not in files:raise ValueError('bundle manifest missing')
    m=loads(files[NAME].decode('utf8'));exact(m,('schema_version','name','version','source','files'))
    if type(m['schema_version']) is not int or m['schema_version']!=1 or m['name']!='ai-dev-execution' or m['source']!='dreampia-private-authored':raise ValueError('invalid bundle identity')
    if not isinstance(m['version'],str) or not re.fullmatch(r'\d+\.\d+\.\d+',m['version']) or version is not None and m['version']!=version:raise ValueError('bundle version mismatch')
    if not isinstance(m['files'],list) or not m['files'] or len(m['files'])>256:raise ValueError('invalid bundle inventory')
    declared={};missing=[]
    for row in m['files']:
        exact(row,('path','sha256','required'));n=path(row['path'])
        if n in declared or type(row['required']) is not bool or not isinstance(row['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['sha256']):raise ValueError('invalid bundle entry')
        declared[n]=row
        if n not in files:
            if row['required']:raise ValueError('required bundle file missing: '+n)
            missing.append(n)
        elif sha(files[n])!=row['sha256']:raise ValueError('bundle hash mismatch: '+n)
    if 'SKILL.md' not in declared or not declared['SKILL.md']['required']:raise ValueError('required skill entry missing')
    if set(files)-set(declared)-{NAME}:raise ValueError('undeclared bundle file')
    text=files['SKILL.md'].decode('utf8');parts=text.split('---',2)
    if len(parts)!=3 or parts[0].strip():raise ValueError('invalid skill frontmatter')
    fields={}
    for line in parts[1].splitlines():
        if line.strip():
            k,v=line.split(':',1)
            if k.strip() in fields:raise ValueError('duplicate skill frontmatter')
            fields[k.strip()]=v.strip()
    if set(fields)!= {'name','description'} or fields['name']!='ai-dev-execution' or not fields['description']:raise ValueError('invalid skill identity')
    return {'name':m['name'],'version':m['version'],'source':m['source'],'manifest_sha256':sha(files[NAME]),'resolved':sorted(set(files)-{NAME}),'missing_optional':sorted(missing)}
def read(root) -> dict[str, bytes]:
    root=pathlib.Path(root);files={}
    if root.is_symlink() or not root.is_dir():raise ValueError('invalid skill root')
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('bundle symlink')
        if p.is_file():files[p.relative_to(root).as_posix()]=p.read_bytes()
        elif not p.is_dir():raise ValueError('bundle special file')
    return files
def write(root,version) -> dict[str, object]:
    root=pathlib.Path(root);files=read(root);files.pop(NAME,None)
    m={'schema_version':1,'name':'ai-dev-execution','version':version,'source':'dreampia-private-authored','files':[{'path':path(n),'sha256':sha(data),'required':True} for n,data in sorted(files.items())]}
    encoded=(json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode();validate({**files,NAME:encoded},version)
    (root/NAME).write_bytes(encoded)
    return validate({**files,NAME:encoded},version)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['write','check']);p.add_argument('root');p.add_argument('--version',required=True);a=p.parse_args()
    print(json.dumps(write(a.root,a.version) if a.action=='write' else validate(read(a.root),a.version),ensure_ascii=False,indent=2))
