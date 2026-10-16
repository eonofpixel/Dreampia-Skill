import copy, json, pathlib, sys, tempfile, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import core, schema, codex_adapter, eval_runner
import test_product
ROOT=pathlib.Path(__file__).resolve().parents[2]

class StrictContractTests(unittest.TestCase):
    def plan(self):
        return {'version':1,'requirements':['R1'],'tasks':[{'id':'T1','requirements':['R1'],'adapter':{'kind':'deterministic'},'checks':[{'id':'C1','argv':[sys.executable,'-c','pass']}]}]}
    def test_unknown_fields_every_manifest_level(self):
        for level in ('manifest','task','adapter','check'):
            m=self.plan();t=m['tasks'][0];target={'manifest':m,'task':t,'adapter':t['adapter'],'check':t['checks'][0]}[level];target['typo']=1
            with self.subTest(level=level),self.assertRaises(ValueError):core.validate(m)
    def test_execution_bound_and_type_edges(self):
        for key,values in [('timeout',[True,0,-1,float('inf'),float('nan'),3601,10**400]),('max_attempts',[True,0,-1,1.5,11,10**400])]:
            for value in values:
                m=self.plan();m['tasks'][0][key]=value
                with self.subTest(key=key,value=str(value)),self.assertRaises(ValueError):core.validate(m)
        for key in ('delay','fail_attempts'):
            for value in (True,float('inf'),10**400):
                m=self.plan();m['tasks'][0]['adapter'][key]=value
                with self.subTest(key=key,value=str(value)),self.assertRaises(ValueError):core.validate(m)
    def test_json_duplicates_and_nonfinite_tokens(self):
        for raw in ('{"version":1,"version":2}','{"budget":Infinity}','{"delay":NaN}'):
            with self.assertRaises(ValueError):schema.loads(raw)
    def test_model_and_reasoning_cannot_upgrade(self):
        for extra in ({'model':'larger-model'},{'reasoning_effort':'high'}):
            m=self.plan();m['tasks'][0]['adapter']={'kind':'codex','prompt':'fixture',**extra}
            with self.assertRaises(ValueError):core.validate(m)
    def test_ownership_disjoint_and_overlapping(self):
        m=self.plan();t=m['tasks'][0];t.update(owner='impl',owns=['src']);m['tasks'].append({**copy.deepcopy(t),'id':'T2','owner':'review','owns':['tests'],'checks':[{'id':'C2','argv':[sys.executable,'-c','pass']}]})
        core.validate(m)
        for owns in (['src'],['src/file.py'],['../outside'],['SRC'],['SRC/file.py']):
            m['tasks'][1]['owns']=owns
            with self.assertRaises(ValueError):core.validate(m)
    def test_ownership_types_and_pair(self):
        for extra in ({'owner':False,'owns':['src']},{'owner':'impl'},{'owns':['src']},{'owner':'impl','owns':['src','src']}):
            m=self.plan();m['tasks'][0].update(extra)
            with self.assertRaises(ValueError):core.validate(m)
    def test_eval_bound_rejects_large_integer_without_traceback(self):
        fixture=test_product.ProductTests();fixture.setUp()
        try:
            out,data=fixture.audited()
            for value in (True,0,-1,3601,10**400):
                for r in data['records']:r['controls']['time_budget_seconds']=value
                (out/'results.json').write_text(json.dumps(data))
                with self.assertRaises(ValueError):eval_runner.aggregate(ROOT/'evals/suite.json',out/'results.json')
        finally:fixture.tearDown()
    def test_probe_cancel_cleans_group_and_fast(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);exe=root/'fake';marker=root/'survived';pid=root/'started'
            child="import pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path(%r).write_text('ready');time.sleep(1.5);pathlib.Path(%r).write_text('bad')"%(str(pid),str(marker))
            exe.write_text('#!'+sys.executable+'\nimport subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",'+repr(child)+'])\ntime.sleep(10)');exe.chmod(0o700)
            began=time.monotonic();result=codex_adapter.probe(str(exe),timeout=5,stopped=lambda:pid.exists())
            self.assertEqual(result['category'],'PROBE_CANCELLED');self.assertLess(time.monotonic()-began,2)
            time.sleep(1.6);self.assertFalse(marker.exists())
    def test_locked_suite_path_escape_and_unknown_key_rejected_before_prepare(self):
        import hashlib
        for patch in ('split','key','file','root','request-child','case-file','unicode-file','case-id'):
            with tempfile.TemporaryDirectory() as tmp:
                root=pathlib.Path(tmp);suite=json.loads((ROOT/'evals/suite.json').read_text())
                if patch=='split':suite['scenarios'][0]['split']='../outside'
                elif patch=='key':suite['scenarios'][0]['typo']=1
                elif patch=='file':suite['scenarios'][0]['files']['../outside']='bad'
                elif patch=='root':suite['scenarios'][0]['files']['.']='bad'
                elif patch=='request-child':suite['scenarios'][0]['files']['request.txt/nested']='bad'
                elif patch=='case-file':suite['scenarios'][0]['files'].update(same='A',SAME='B')
                elif patch=='unicode-file':suite['scenarios'][0]['files'].update({'café':'A','cafe\u0301':'B'})
                else:suite['scenarios'][1]['id']='e1'
                data=json.dumps(suite).encode();path=root/'suite.json';path.write_bytes(data);(root/'suite.lock.json').write_text(json.dumps({'version':1,'sha256':hashlib.sha256(data).hexdigest()}))
                with self.assertRaises(ValueError):eval_runner.prepare(path,root/'out')
                self.assertFalse((root/'out').exists())
