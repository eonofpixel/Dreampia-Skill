"""Offline preparation/aggregation of audited A/B results; never calls a model."""
import argparse,hashlib,json,pathlib,sys,math,unicodedata
try:
    from .schema import loads
except ImportError:
    from schema import loads

def fields(value,allowed,required=()) -> None:
    if not isinstance(value,dict) or set(value)-set(allowed) or set(required)-set(value):raise ValueError('unknown or missing evaluation field')

def read_suite(path) -> tuple[dict[str, object], str]:
    path=pathlib.Path(path).resolve();data=path.read_bytes()
    lock=loads(path.with_name('suite.lock.json').read_text())
    fields(lock,('version','sha256'),('version','sha256'))
    if type(lock['version']) is not int or lock['version']!=1:raise ValueError('invalid suite lock')
    if hashlib.sha256(data).hexdigest()!=lock['sha256']:raise ValueError('suite lock mismatch')
    suite=loads(data)
    fields(suite,('version','status','controls','scenarios'),('version','status','controls','scenarios'))
    if type(suite['version']) is not int or suite['version']!=1 or suite['status']!='NOT_RUN' or suite['controls']!=['model','host','time_budget_seconds','toolset','initial_source','scenario_digest'] or not isinstance(suite['scenarios'],list) or not suite['scenarios']:raise ValueError('invalid suite')
    ids=set();splits=set()
    for case in suite['scenarios']:
        fields(case,('id','prompt','checks','split','files'),('id','prompt','checks','split','files'))
        if not isinstance(case['id'],str) or not __import__('re').fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}',case['id']) or case['id'].casefold() in ids:raise ValueError('invalid scenario ID')
        ids.add(case['id'].casefold())
        if case['split'] not in ('baseline','holdout'):raise ValueError('invalid split')
        splits.add(case['split'])
        if not isinstance(case['prompt'],str) or not case['prompt'].strip() or not isinstance(case['checks'],list) or not case['checks'] or any(not isinstance(x,str) or not x for x in case['checks']) or len(set(case['checks']))!=len(case['checks']) or not isinstance(case['files'],dict):raise ValueError('invalid scenario')
        for name,content in case['files'].items():
            rel=pathlib.PurePosixPath(name)
            if not isinstance(content,str) or not name or '\x00' in name or '\\' in name or rel.is_absolute() or '..' in rel.parts or rel.as_posix()!=name or not rel.parts or unicodedata.normalize('NFC',name).casefold()=='request.txt' or unicodedata.normalize('NFC',name).casefold().startswith('request.txt/'):raise ValueError('invalid scenario file')
        names=[unicodedata.normalize('NFC',name).casefold() for name in case['files']]
        if len(set(names))!=len(names) or any(a!=b and b.startswith(a+'/') for a in names for b in names):raise ValueError('file/directory conflict')
    if splits!={'baseline','holdout'}:raise ValueError('baseline and holdout required')
    return suite,lock['sha256']

def safe_path(root,value) -> pathlib.Path:
    if not isinstance(value,str) or not value:raise ValueError('path required')
    rel=pathlib.PurePosixPath(value)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('path escape')
    path=root.joinpath(*rel.parts)
    for p in [path,*path.parents]:
        if p==root.parent:break
        if p.is_symlink():raise ValueError('symlink')
        if p==root:break
    try:path.resolve().relative_to(root.resolve())
    except ValueError:raise ValueError('path escape')
    return path

def case_controls(case) -> dict[str, str]:
    encode=lambda value:json.dumps(value,sort_keys=True,ensure_ascii=False).encode()
    return {'initial_source':hashlib.sha256(encode(case['files'])).hexdigest(),
            'scenario_digest':hashlib.sha256(encode(case)).hexdigest()}

def prepare(suite_path,destination) -> dict[str, object]:
    suite,frozen=read_suite(suite_path);dest=pathlib.Path(destination).resolve()
    if dest.exists():raise ValueError('destination exists')
    dest.mkdir(parents=True);records=[]
    for case in suite['scenarios']:
        for arm in ('without_skill','with_skill'):
            root=dest/case['split']/case['id']/arm;root.mkdir(parents=True)
            for name,value in case['files'].items():
                path=safe_path(root,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
            (root/'request.txt').write_text(case['prompt'])
            records.append({'scenario':case['id'],'split':case['split'],'arm':arm,'status':'NOT_RUN',
                'suite_digest':frozen,'controls':{**{k:None for k in suite['controls']},**case_controls(case)},'judgments':[]})
    result={'version':1,'records':records};(dest/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return {'prepared':True,'scenarios':len(suite['scenarios']),'arms':len(records),'model_calls':0,'results':str(dest/'results.json')}

def aggregate(suite_path,submission_path) -> dict[str, object]:
    suite,frozen=read_suite(suite_path);path=pathlib.Path(submission_path).resolve();root=path.parent
    submission=loads(path.read_text());cases={x['id']:x for x in suite['scenarios']};seen={};validated=[]
    fields(submission,('version','records'),('version','records'))
    if type(submission.get('version')) is not int or submission.get('version')!=1 or not isinstance(submission.get('records'),list):raise ValueError('invalid submission')
    for r in submission['records']:
        fields(r,('scenario','split','arm','status','suite_digest','controls','judgments','critical_failures'),('scenario','split','arm','status','suite_digest','controls','judgments'))
        key=(r.get('scenario'),r.get('arm'))
        if key in seen or key[0] not in cases or key[1] not in ('without_skill','with_skill'):raise ValueError('unknown or duplicate result')
        case=cases[key[0]]
        if r.get('split')!=case['split'] or r.get('suite_digest')!=frozen:raise ValueError('scenario mismatch')
        if r.get('status') not in ('PASS','FAIL','NOT_RUN'):raise ValueError('invalid status')
        seen[key]=r
        if r['status']=='NOT_RUN':continue
        controls=r.get('controls',{})
        if set(controls)!=set(suite['controls']) or any(v is None for v in controls.values()):raise ValueError('execution controls missing')
        if any(controls.get(k)!=v for k,v in case_controls(case).items()):raise ValueError('initial inputs differ')
        if not isinstance(controls['model'],str) or not controls['model'] or not isinstance(controls['host'],str) or not controls['host'] or not isinstance(controls['toolset'],list) or not controls['toolset'] or any(not isinstance(x,str) or not x for x in controls['toolset']) or type(controls['time_budget_seconds']) not in (int,float) or not 0<controls['time_budget_seconds']<=3600 or not math.isfinite(controls['time_budget_seconds']):raise ValueError('invalid execution controls')
        critical=r.get('critical_failures',[])
        if not isinstance(critical,list) or any(x not in ('UNAUTHORIZED_CHANGE','SECRET_EXPOSURE','FALSE_COMPLETE','USER_WORK_LOSS') for x in critical):raise ValueError('invalid critical failures')
        judgments=r.get('judgments',[])
        if not isinstance(judgments,list) or len(judgments)!=len(case['checks']) or {j.get('criterion') for j in judgments}!=set(case['checks']):raise ValueError('rubric missing')
        score=0
        for j in judgments:
            fields(j,('criterion','score','evidence','sha256'),('criterion','score','evidence','sha256'))
            if type(j.get('score')) is not int or not 0<=j['score']<=2:raise ValueError('invalid score')
            evidence=safe_path(root,j['evidence'])
            if not evidence.is_file() or hashlib.sha256(evidence.read_bytes()).hexdigest()!=j.get('sha256'):raise ValueError('evidence mismatch')
            score+=j['score']
        validated.append({'scenario':key[0],'arm':key[1],'split':case['split'],'score':score,'maximum':2*len(case['checks']),'controls':controls,'critical_failures':r.get('critical_failures',[])})
    pairs=[]
    for case in cases.values():
        a=next((x for x in validated if x['scenario']==case['id'] and x['arm']=='without_skill'),None)
        b=next((x for x in validated if x['scenario']==case['id'] and x['arm']=='with_skill'),None)
        if a and b:
            if a['controls']!=b['controls']:raise ValueError('paired controls differ')
            pairs.append({'scenario':case['id'],'split':case['split'],'without_skill':a['score'],'with_skill':b['score'],'maximum':a['maximum'],'difference':b['score']-a['score']})
    groups={}
    for split in ('baseline','holdout'):
        subset=[x for x in pairs if x['split']==split];required=sum(x['split']==split for x in cases.values())
        groups[split]={'status':'COMPLETE' if len(subset)==required else 'NOT_RUN_OR_INCOMPLETE','pairs':len(subset),'required':required,
            'difference_total':sum(x['difference'] for x in subset) if len(subset)==required else None}
    complete=all(x['status']=='COMPLETE' for x in groups.values())
    return {'status':'COMPLETE_AUDITED_RECORDS' if complete else 'NOT_RUN_OR_INCOMPLETE','model_calls_by_runner':0,
            'score_kind':'human-audited records; not automatic AI quality certification','groups':groups,'pairs':pairs,'critical_failures':[{k:v for k,v in x.items() if k in ('scenario','arm','critical_failures')} for x in validated if x['critical_failures']],
            'effect_score':sum(x['difference'] for x in pairs) if complete else None}

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description='Offline fixed-suite evaluation (no provider execution)')
    p.add_argument('action',choices=['prepare','aggregate']);p.add_argument('suite');p.add_argument('path');a=p.parse_args(argv)
    try:out=prepare(a.suite,a.path) if a.action=='prepare' else aggregate(a.suite,a.path)
    except (ValueError,TypeError,KeyError,OSError) as e:
        print(json.dumps({'error':'INVALID_EVALUATION_INPUT','type':type(e).__name__}));return 2
    print(json.dumps(out,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':sys.exit(main())
