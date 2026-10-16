"""Opt-in byte-backed handoff checks. Not identity authentication or semantic certification."""
import argparse,hashlib,json,pathlib
ROLES={'planner','architect','analyst','executor','reviewer','verifier','ux-designer','privacy-guard','doc-writer'}
KINDS={'appearance','behavior','persistence','security'}
STATUSES={'PASS','FAIL','NOT_RUN','BLOCKED'}
def _resolve_role(value):
 if not isinstance(value,str):return ''
 if value in ROLES:return value
 try:
  try:from . import route_planner
  except ImportError:import route_planner
  return route_planner.resolve_role_alias(value)
 except ValueError:return value
def relative(value) -> pathlib.PurePosixPath:
 if not isinstance(value,str) or not value or '\\' in value or '\x00' in value:raise ValueError('invalid relative path')
 p=pathlib.PurePosixPath(value)
 if p.is_absolute() or p.as_posix()!=value or any(x in ('.','..') for x in p.parts):raise ValueError('path escapes ownership')
 return p

def validate(contract,root,*,strict_png=False,before_inventory=None,after_inventory=None) -> dict[str, object]:
 root=pathlib.Path(root).resolve()
 if not isinstance(contract,dict) or set(contract)!={'task_id','from_role','to_role','scope','owned_paths','constraints','unresolved','acceptance'}:raise ValueError('invalid handoff fields')
 for k in ('task_id','scope'):
  if not isinstance(contract[k],str) or not contract[k].strip():raise ValueError('missing identity or scope')
 from_role=_resolve_role(contract['from_role']);to_role=_resolve_role(contract['to_role'])
 if from_role not in ROLES or to_role not in ROLES or from_role==to_role:raise ValueError('distinct recognized roles required')
 for k in ('owned_paths','constraints','unresolved'):
  if not isinstance(contract[k],list) or any(not isinstance(x,str) or not x.strip() for x in contract[k]):raise ValueError('invalid handoff list')
 if not contract['owned_paths']:raise ValueError('ownership missing')
 for p in contract['owned_paths']:relative(p)
 if before_inventory is not None or after_inventory is not None:
  if before_inventory is None or after_inventory is None:raise ValueError('both before_inventory and after_inventory required')
  try:from . import write_boundary
  except ImportError:import write_boundary
  bcheck=write_boundary.verify_write_boundary(before_inventory,after_inventory,contract['owned_paths'])
  if bcheck['status']!='PASS':raise ValueError('write boundary violation: '+','.join(bcheck['detail_codes']))
 rows=contract['acceptance']
 if not isinstance(rows,list) or not rows:raise ValueError('acceptance missing')
 ids=set();ready=not contract['unresolved'];checked=[]
 for row in rows:
  if not isinstance(row,dict) or set(row)!={'id','kind','status','evidence'}:raise ValueError('invalid acceptance')
  if not isinstance(row['id'],str) or not row['id'].strip() or row['id'] in ids:raise ValueError('duplicate or missing criterion')
  ids.add(row['id'])
  if row['kind'] not in KINDS or row['status'] not in STATUSES or not isinstance(row['evidence'],list):raise ValueError('invalid verdict')
  if row['status']!='PASS':ready=False;continue
  if not row['evidence']:raise ValueError('PASS without evidence')
  if row['kind']=='appearance' and not any(isinstance(e,dict) and e.get('kind')=='screenshot' for e in row['evidence']):raise ValueError('appearance requires screenshot evidence')
  for e in row['evidence']:
   if not isinstance(e,dict) or set(e)!={'path','sha256','kind','status','exit_code'}:raise ValueError('invalid evidence fields')
   rel=relative(e['path']);p=root.joinpath(*rel.parts)
   current=root
   for part in rel.parts:
    current=current/part
    if current.is_symlink():raise ValueError('evidence symlink forbidden')
   raw_bytes=p.read_bytes() if p.is_file() else None
   if raw_bytes is None or e['sha256']!=hashlib.sha256(raw_bytes).hexdigest():raise ValueError('missing or stale evidence')
   if e['kind'] not in {'screenshot','test-log','trace-json'} or e['status']!='PASS':raise ValueError('contradictory evidence verdict')
   if e['kind']=='screenshot':
    if row['kind']!='appearance' or e['exit_code'] is not None:raise ValueError('screenshots prove appearance, not behavior')
    if strict_png:
     try:from . import visual_acceptance
     except ImportError:import visual_acceptance
     visual_acceptance.decode_png_bytes(raw_bytes)
   elif type(e['exit_code']) is not int or e['exit_code']!=0:raise ValueError('successful execution required')
   checked.append(e['path'])
 return {'ready':ready,'scope':contract['scope'],'criteria':len(ids),'checked_evidence':checked,'limitations':'byte/metadata checks only; reviewer must inspect meaning; role names do not prove independent actors'}

def main() -> int:
 p=argparse.ArgumentParser();p.add_argument('contract');p.add_argument('--project',required=True);p.add_argument('--strict-png',action='store_true');a=p.parse_args()
 try:r=validate(json.loads(pathlib.Path(a.contract).read_text()),a.project,strict_png=a.strict_png)
 except (ValueError,OSError,TypeError) as e:print(json.dumps({'ready':False,'error':str(e)}));return 2
 print(json.dumps(r,ensure_ascii=False));return 0 if r['ready'] else 1
if __name__=='__main__':raise SystemExit(main())
