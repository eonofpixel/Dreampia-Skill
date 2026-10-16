import json, pathlib, tempfile, unittest, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import core

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / 'source.txt').write_text('current')
    def tearDown(self): self.tmp.cleanup()
    def manifest(self, command=None, **task):
        t = {'id':'T1','requirements':['R1'],'depends_on':[], 'adapter':{'kind':'deterministic'},
             'checks':[{'id':'C1','argv':command or [sys.executable,'-c','pass']}], **task}
        m = {'version':1,'requirements':['R1'],'tasks':[t]}
        (self.root/'harness.json').write_text(json.dumps(m))
        return m
    def test_missing_check_rejected(self):
        m=self.manifest(checks=[])
        with self.assertRaises(ValueError): core.validate(m)
    def test_unknown_dependency_rejected(self):
        with self.assertRaises(ValueError): core.validate(self.manifest(depends_on=['missing']))
    def test_failed_verification_never_completes(self):
        self.manifest([sys.executable,'-c','raise SystemExit(7)'])
        state=core.run(self.root)
        self.assertEqual(state['tasks'].get('T1',{}).get('status'),'failed')
    def test_pass_has_source_evidence(self):
        self.manifest()
        state=core.run(self.root)
        self.assertEqual(state['tasks'].get('T1',{}).get('status'),'verified')
        self.assertEqual(state['tasks']['T1']['evidence']['source'],core.source_hash(self.root))
    def test_stale_evidence(self):
        self.manifest(); core.run(self.root)
        (self.root/'source.txt').write_text('changed')
        self.assertEqual(core.status(self.root)['tasks']['T1']['status'],'stale')
    def test_not_run(self):
        self.manifest(['/definitely/missing/executable'])
        q=core.run(self.root)['tasks']['T1']
        self.assertEqual(q['status'],'failed')
        self.assertEqual(q['last_checks'][0]['result'],'NOT_RUN')
    def test_source_changes_during_check(self):
        self.manifest([sys.executable,'-c',"open('source.txt','a').write('mutation')"])
        q=core.run(self.root)['tasks']['T1']
        self.assertEqual(q['status'],'failed')
        self.assertNotIn('evidence',q)
    def test_retry_exhausted_and_persisted(self):
        self.manifest(adapter={'kind':'deterministic','fail_attempts':10},max_attempts=2)
        self.assertEqual(core.run(self.root)['tasks']['T1']['attempts'],2)
        q=core.run(self.root)['tasks']['T1']
        self.assertEqual(q['status'],'failed'); self.assertEqual(q['attempts'],2)
    def test_retry_recovers(self):
        self.manifest(adapter={'kind':'deterministic','fail_attempts':1})
        q=core.run(self.root)['tasks']['T1']
        self.assertEqual(q['status'],'verified'); self.assertEqual(q['attempts'],2)
    def test_timeout(self):
        self.manifest([sys.executable,'-c','import time; time.sleep(10)'],timeout=.08,max_attempts=1)
        q=core.run(self.root)['tasks']['T1']
        self.assertEqual(q['last_checks'][0]['result'],'TIMEOUT')
    def test_cycle(self):
        m=self.manifest(); t=m['tasks'][0]; t['depends_on']=['T2']
        m['tasks'].append({**t,'id':'T2','depends_on':['T1'],'checks':[{'id':'C2','argv':[sys.executable,'-c','pass']}]})
        with self.assertRaises(ValueError): core.validate(m)
    def test_failed_dependency_blocks(self):
        m=self.manifest([sys.executable,'-c','raise SystemExit(1)'],max_attempts=1)
        m['tasks'].append({'id':'T2','requirements':['R1'],'depends_on':['T1'],'adapter':{'kind':'deterministic'},'checks':[{'id':'C2','argv':[sys.executable,'-c','pass']}]})
        (self.root/'harness.json').write_text(json.dumps(m))
        self.assertEqual(core.run(self.root)['tasks']['T2']['status'],'blocked')
    def test_resume_skips_verified(self):
        self.manifest(); first=core.run(self.root); second=core.run(self.root)
        self.assertEqual(first['tasks']['T1']['evidence'],second['tasks']['T1']['evidence'])
        self.assertEqual(second['tasks']['T1']['attempts'],1)
    def test_plan_change_invalidates(self):
        self.manifest(); core.run(self.root)
        self.manifest([sys.executable,'-c','raise SystemExit(2)'])
        self.assertEqual(core.status(self.root)['tasks']['T1']['status'],'recovery_hold')
        self.assertEqual(core.reverify(self.root)['tasks']['T1']['status'],'failed')
    def test_event_secret_minimization(self):
        secret='FAKE_SECRET_abcdef123456'
        self.manifest([sys.executable,'-c',f"print('{secret}')"])
        core.run(self.root)
        data=''.join(p.read_text() for p in (self.root/'.harness').iterdir() if p.is_file())
        self.assertNotIn(secret,data)
    def test_duplicate_lock(self):
        self.manifest()
        with core.locked(core.state_dir(self.root)):
            with self.assertRaises(RuntimeError): core.run(self.root)
    def test_atomic_failure_keeps_previous(self):
        from unittest.mock import patch
        p=self.root/'state.json'; core.atomic(p,{'old':1})
        with patch('core.os.replace',side_effect=OSError('injected')):
            with self.assertRaises(OSError): core.atomic(p,{'new':2})
        self.assertEqual(json.loads(p.read_text()),{'old':1})
        self.assertEqual(len(list(self.root.glob('*.tmp'))),0)
    def test_symlink_source_rejected(self):
        self.manifest(); (self.root/'alias').symlink_to(self.root/'source.txt')
        with self.assertRaises(ValueError): core.run(self.root)
    def test_trace_current_links(self):
        self.manifest(); core.run(self.root)
        row=core.trace(self.root)[0]
        self.assertEqual((row['requirement'],row['task'],row['check']),('R1','T1','C1'))
        self.assertTrue(row['current']); self.assertEqual(row['result'],'PASS')
        (self.root/'source.txt').write_text('stale')
        self.assertFalse(core.trace(self.root)[0]['current'])
    def test_later_edits_reverify_earlier_source(self):
        m=self.manifest(); t=m['tasks'][0]
        m['tasks'].append({**t,'id':'T2','depends_on':['T1'],
            'adapter':{'kind':'command','argv':[sys.executable,'-c',"open('new.txt','w').write('v')"]},
            'checks':[{'id':'C2','argv':[sys.executable,'-c','pass']}]})
        (self.root/'harness.json').write_text(json.dumps(m))
        s=core.run(self.root)
        for q in s['tasks'].values():
            self.assertEqual(q['status'],'verified')
            self.assertEqual(q['evidence']['source'],core.source_hash(self.root))
    def test_state_and_events_excluded_from_hash(self):
        self.manifest(); core.run(self.root); before=core.source_hash(self.root)
        (self.root/'.harness/debug.txt').write_text('state-only')
        core.cancel(self.root)
        self.assertEqual(before,core.source_hash(self.root))
        self.assertEqual(core.status(self.root)['tasks']['T1']['status'],'verified')
    def test_failed_adapter_can_repeat_side_effects(self):
        script="from pathlib import Path; p=Path('effect.txt'); p.write_text((p.read_text() if p.exists() else '')+'x'); raise SystemExit(1)"
        self.manifest(adapter={'kind':'command','argv':[sys.executable,'-c',script]},max_attempts=2)
        q=core.run(self.root)['tasks']['T1']
        self.assertEqual(q['status'],'failed'); self.assertEqual((self.root/'effect.txt').read_text(),'xx')
    def test_corrupt_check_evidence_is_not_current(self):
        m=self.manifest(); s=core.run(self.root)
        q=s['tasks']['T1']; q['evidence']['checks'][0].update(id='WRONG',argv_digest='0'*64,exit_code=17)
        self.assertFalse(core.fresh(q,m['tasks'][0],core.source_hash(self.root)))
        core.atomic(self.root/'.harness/state.json',s)
        self.assertEqual(core.status(self.root)['tasks']['T1']['status'],'stale')
        self.assertFalse(core.trace(self.root)[0]['current'])
