import hashlib,json,pathlib,tempfile,unittest,sys,subprocess,os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import build,eval_runner
ROOT=pathlib.Path(__file__).resolve().parents[2]
class ProductTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_zipapp_runs_version(self):
        p=self.root/'harness-0.7.0.pyz';build.build(p)
        r=subprocess.run([sys.executable,str(p),'--version'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0);self.assertEqual(r.stdout.strip(),'0.7.0')
        with self.assertRaises(ValueError):build.build(p)
    def test_module_entrypoint(self):
        r=subprocess.run([sys.executable,'-m','harness','--version'],cwd=ROOT,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        self.assertEqual(r.returncode,0);self.assertEqual(r.stdout.strip(),(ROOT/'VERSION').read_text().strip())
    def test_fixed_eval_prepare_does_not_score_not_run(self):
        out=self.root/'eval';eval_runner.prepare(ROOT/'evals/suite.json',out)
        result=eval_runner.aggregate(ROOT/'evals/suite.json',out/'results.json')
        self.assertEqual(result['status'],'NOT_RUN_OR_INCOMPLETE');self.assertIsNone(result['effect_score'])
        self.assertEqual(result['groups']['baseline']['required'],2);self.assertEqual(result['groups']['holdout']['required'],2)
    def audited(self):
        out=self.root/'eval';eval_runner.prepare(ROOT/'evals/suite.json',out)
        data=json.loads((out/'results.json').read_text());suite,_=eval_runner.read_suite(ROOT/'evals/suite.json')
        proof=out/'proof.txt';proof.write_text('Synthetic fixture evidence; NOT a model evaluation.')
        digest=hashlib.sha256(proof.read_bytes()).hexdigest()
        cases={c['id']:c for c in suite['scenarios']}
        for r in data['records']:
            r['status']='PASS';r['controls'].update(model='fixture-model',host='fixture-host',time_budget_seconds=10,toolset=['fixture'])
            r['judgments']=[{'criterion':c,'score':1,'evidence':'proof.txt','sha256':digest} for c in cases[r['scenario']]['checks']]
        (out/'results.json').write_text(json.dumps(data));return out,data
    def test_eval_aggregation_fixture_only(self):
        out,data=self.audited();r=eval_runner.aggregate(ROOT/'evals/suite.json',out/'results.json')
        self.assertEqual(r['status'],'COMPLETE_AUDITED_RECORDS');self.assertEqual(r['effect_score'],0)
    def test_eval_missing_evidence_rejected(self):
        out,data=self.audited();(out/'proof.txt').write_text('modified')
        with self.assertRaises(ValueError):eval_runner.aggregate(ROOT/'evals/suite.json',out/'results.json')
    def test_eval_control_mismatch_rejected(self):
        out,data=self.audited();data['records'][1]['controls']['model']='different'
        (out/'results.json').write_text(json.dumps(data))
        with self.assertRaises(ValueError):eval_runner.aggregate(ROOT/'evals/suite.json',out/'results.json')
    def test_eval_path_escape_rejected(self):
        with self.assertRaises(ValueError):eval_runner.safe_path(self.root,'../escape')
    def test_eval_lock_rejects_changed_suite(self):
        import shutil
        suite=self.root/'suite.json';shutil.copyfile(ROOT/'evals/suite.json',suite);shutil.copyfile(ROOT/'evals/suite.lock.json',self.root/'suite.lock.json');suite.write_text('{}')
        with self.assertRaises(ValueError):eval_runner.read_suite(suite)
