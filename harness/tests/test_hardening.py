import json, pathlib, sys, tempfile, unittest, subprocess
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import core
CLI=pathlib.Path(core.__file__).with_name('cli.py')
class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        (self.root/'source.txt').write_text('good')
        self.plan()
    def tearDown(self): self.tmp.cleanup()
    def plan(self,command=None):
        m={'version':1,'requirements':['R1'],'tasks':[{'id':'T1','requirements':['R1'],'depends_on':[], 'max_attempts':2,'adapter':{'kind':'command','argv':[sys.executable,'-c',"from pathlib import Path;p=Path('effects');p.write_text((p.read_text() if p.exists() else '')+'x')"]},'checks':[{'id':'C1','argv':command or [sys.executable,'-c','pass']}]}]}
        (self.root/'harness.json').write_text(json.dumps(m));return m
    def test_nested_excluded_names_are_hashed(self):
        for name in ('.harness','.git','__pycache__'):
            p=self.root/'app'/name/'input.txt';p.parent.mkdir(parents=True,exist_ok=True);p.write_text('good')
            before=core.source_hash(self.root);p.write_text('bad')
            self.assertNotEqual(before,core.source_hash(self.root),name)
    def test_ignored_name_input_becomes_stale(self):
        p=self.root/'app/.harness/value';p.parent.mkdir(parents=True);p.write_text('good')
        self.plan([sys.executable,'-c',"from pathlib import Path;assert Path('app/.harness/value').read_text()=='good'"])
        core.run(self.root);p.write_text('bad')
        self.assertEqual(core.status(self.root)['tasks']['T1']['status'],'stale')
    def test_corrupt_trace_is_structured(self):
        s=core.run(self.root);s['tasks']['T1']['evidence']=[];core.atomic(self.root/'.harness/state.json',s)
        r=subprocess.run([sys.executable,str(CLI),'trace',str(self.root)],capture_output=True,text=True)
        self.assertEqual(r.returncode,2);self.assertNotIn('Traceback',r.stderr)
        self.assertEqual(json.loads(r.stdout)['error']['code'],'STATE_CORRUPT')
    def test_recovery_never_restores_done_or_replays(self):
        core.run(self.root);before=(self.root/'effects').read_text()
        (self.root/'.harness/state.json').write_text('{broken')
        result=core.recover(self.root)
        self.assertTrue(result['quarantine'])
        self.assertEqual(core.status(self.root)['tasks']['T1']['status'],'recovery_hold')
        self.assertEqual(core.run(self.root)['tasks']['T1']['status'],'recovery_hold')
        self.assertEqual((self.root/'effects').read_text(),before)
        self.assertEqual(core.reverify(self.root)['tasks']['T1']['status'],'verified')
        self.assertEqual((self.root/'effects').read_text(),before)
    def test_recover_preserves_user_files(self):
        core.run(self.root);(self.root/'.harness/state.json').write_text('bad')
        core.recover(self.root)
        self.assertEqual((self.root/'source.txt').read_text(),'good')
    def test_nested_symlink_rejected(self):
        p=self.root/'app/.harness';p.mkdir(parents=True);(p/'escape').symlink_to('/tmp')
        with self.assertRaises(ValueError):core.source_hash(self.root)
    def test_declared_input_path_escape_rejected(self):
        m=self.plan();m['tasks'][0]['checks'][0]['inputs']=['../outside']
        with self.assertRaises(ValueError):core.validate(m)
    def test_replay_requires_explicit_acknowledgment(self):
        core.run(self.root);core.recover(self.root)
        with self.assertRaises(ValueError):core.authorize_replay(self.root,'T1',False)
        core.authorize_replay(self.root,'T1',True)
        self.assertEqual(core.run(self.root)['tasks']['T1']['status'],'verified')
        self.assertEqual((self.root/'effects').read_text(),'xx')
    def test_executable_mode_changes_invalidate(self):
        script=self.root/'check';script.write_text('#!/bin/sh\nexit 0\n');script.chmod(0o700)
        self.plan(['./check']);core.run(self.root);script.chmod(0o600)
        self.assertEqual(core.status(self.root)['tasks']['T1']['status'],'stale')
    def test_empty_input_directory_changes_invalidate(self):
        p=self.root/'required-dir';p.mkdir()
        self.plan([sys.executable,'-c',"from pathlib import Path;assert Path('required-dir').is_dir()"])
        core.run(self.root);p.rmdir()
        self.assertEqual(core.status(self.root)['tasks']['T1']['status'],'stale')
    def test_generated_declared_input(self):
        m=self.plan();m['tasks'][0]['adapter']['argv']=[sys.executable,'-c',"open('generated','w').write('ok')"]
        m['tasks'][0]['checks'][0]['inputs']=['generated'];(self.root/'harness.json').write_text(json.dumps(m))
        self.assertEqual(core.run(self.root)['tasks']['T1']['status'],'verified')
    def test_corrupt_state_unknown_fields_rejected(self):
        s=core.run(self.root);s['tasks']['T1']['raw_output']='FAKE_SECRET'
        core.atomic(self.root/'.harness/state.json',s)
        with self.assertRaises(core.StateError):core.status(self.root)
    def test_changed_plan_keeps_recovery_hold(self):
        core.run(self.root);core.recover(self.root)
        m=json.loads((self.root/'harness.json').read_text());m['tasks'][0]['timeout']=5
        (self.root/'harness.json').write_text(json.dumps(m))
        self.assertEqual(core.run(self.root)['tasks']['T1']['status'],'recovery_hold')
        self.assertEqual((self.root/'effects').read_text(),'x')
    def test_plan_change_does_not_automatically_repeat_effects(self):
        core.run(self.root)
        m=json.loads((self.root/'harness.json').read_text());m['tasks'][0]['timeout']=5
        (self.root/'harness.json').write_text(json.dumps(m))
        self.assertEqual(core.run(self.root)['tasks']['T1']['status'],'recovery_hold')
        self.assertEqual((self.root/'effects').read_text(),'x')
