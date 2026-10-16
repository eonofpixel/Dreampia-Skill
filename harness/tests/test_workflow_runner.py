"""Real offline adapter integration tests; no model calls or mocks."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class WorkflowRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / 'worker.py').write_text("import json,sys; c=json.load(sys.stdin); print(c['role'])\n")
        self.contract = {
            'version': 1, 'source_files': ['worker.py'],
            'adapters': {'local': {'argv': [sys.executable, 'worker.py']}},
            'tasks': [dict(id='plan', role='planner', adapter='local', depends_on=[],
                           side_effect=False, timeout=2, max_attempts=1)]}
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        (self.root / 'workflow.json').write_text(json.dumps(self.contract))

    def call(self, action, *args):
        return subprocess.run([sys.executable, '-m', 'harness.workflow_runner', action,
                               str(self.root), *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=15)

    def task(self, ident, role='executor', deps=(), **changes):
        return dict(id=ident, role=role, adapter='local', depends_on=list(deps),
                    side_effect=False, timeout=2, max_attempts=1, **changes)

    def test_resume_rejects_passed_checkpoint_without_matching_success_evidence(self):
        self.assertEqual(self.call('run', '--approve-adapter', 'local').returncode, 0)
        path = self.root / '.workflow/state.json'
        original = json.loads(path.read_text())
        mutations = [
            lambda r: r.update(evidence=[]),
            lambda r: r['evidence'][-1].update(result='FAIL', exit_code=7),
            lambda r: r['evidence'][-1].update(exit_code=7),
            lambda r: r['evidence'][-1].update(argv=['/usr/bin/true']),
            lambda r: r['evidence'][-1].update(timeout=999),
            lambda r: r['evidence'][-1].update(source_fingerprint='0'*64),
            lambda r: r['evidence'][-1].pop('finished_at'),
            lambda r: r['evidence'][-1].update(stdout=[]),
            lambda r: r['evidence'][-1].update(cwd='/unrelated/project'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                state = json.loads(json.dumps(original))
                mutate(state['tasks']['plan'])
                path.write_text(json.dumps(state))
                result = self.call('resume')
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        path.write_text(json.dumps(original))
        self.assertEqual(self.call('resume').returncode, 0)

    def test_dependency_failure(self):
        (self.root / 'worker.py').write_text('import sys; sys.exit(7)')
        self.contract['tasks'].append(self.task('execute', deps=['plan']))
        self.save()
        result = self.call('run', '--approve-adapter', 'local')
        self.assertEqual(result.returncode, 1, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual(state['tasks']['execute']['status'], 'blocked')
        self.assertEqual(state['tasks']['execute']['attempts'], 0)

    def test_timeout_retries_and_bounded_resume(self):
        (self.root / 'worker.py').write_text('import time; time.sleep(5)')
        self.contract['tasks'][0].update(timeout=.05, max_attempts=2)
        self.save()
        result = self.call('run', '--approve-adapter', 'local')
        self.assertEqual(result.returncode, 1, result.stderr)
        row = json.loads(result.stdout)['tasks']['plan']
        self.assertEqual(row['attempts'], 2)
        self.assertEqual([e['result'] for e in row['evidence']], ['TIMEOUT', 'TIMEOUT'])
        self.assertEqual(self.call('resume', '--approve-adapter', 'local').returncode, 1)
        self.assertEqual(json.loads(self.call('status').stdout)['tasks']['plan']['attempts'], 2)

    def test_resume_after_interrupted_read_only_attempt(self):
        self.assertEqual(self.call('run', '--approve-adapter', 'local').returncode, 0)
        path = self.root / '.workflow/state.json'
        state = json.loads(path.read_text())
        state['tasks']['plan'].update(status='running', attempts=1)
        self.contract['tasks'][0]['max_attempts'] = 2
        self.save()
        # New contract must reject the old checkpoint, even if only limits changed.
        path.write_text(json.dumps(state))
        self.assertEqual(self.call('resume', '--approve-adapter', 'local').returncode, 2)

    def test_side_effect_requires_approval_and_never_replays(self):
        (self.root / 'worker.py').write_text("from pathlib import Path; p=Path('count'); p.write_text(p.read_text()+'x' if p.exists() else 'x'); raise SystemExit(7)")
        self.contract['tasks'][0].update(side_effect=True, max_attempts=3)
        self.save()
        self.assertEqual(self.call('run', '--approve-adapter', 'local').returncode, 2)
        self.assertFalse((self.root / 'count').exists())
        result = self.call('run', '--approve-adapter', 'local', '--approve-effect', 'plan')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.call('resume', '--approve-adapter', 'local', '--approve-effect', 'plan').returncode, 1)
        self.assertEqual((self.root / 'count').read_text(), 'x')
        self.assertEqual(json.loads(self.call('status').stdout)['tasks']['plan']['status'], 'needs_reconciliation')

    def test_missing_adapter_and_unapproved_adapter_fail_closed(self):
        self.assertEqual(self.call('run').returncode, 2)
        self.assertFalse((self.root / '.workflow/state.json').exists())
        self.contract['tasks'][0]['adapter'] = 'missing'
        self.save()
        self.assertEqual(self.call('plan').returncode, 2)

    def test_unsafe_contracts_fail_closed(self):
        original = json.loads(json.dumps(self.contract))
        mutations = [lambda c: c.update(source_files=['../secret']),
                     lambda c: c['tasks'][0].update(role='fake'),
                     lambda c: c['tasks'][0].update(depends_on=['plan']),
                     lambda c: c['tasks'][0].update(timeout=0),
                     lambda c: c['tasks'][0].update(max_attempts=999),
                     lambda c: c['tasks'][0].update(side_effect='false'),
                     lambda c: c['adapters']['local'].update(argv=['/bin/sh', '-c', 'touch owned']),
                     lambda c: c['adapters']['local'].update(argv=[sys.executable, '../outside.py']),
                     lambda c: c['tasks'][0].update(shell=True)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.contract = json.loads(json.dumps(original))
                mutate(self.contract)
                self.save()
                self.assertEqual(self.call('plan').returncode, 2)
        self.contract = original
        self.save()
        (self.root / '.workflow').symlink_to(self.root.parent, target_is_directory=True)
        self.assertEqual(self.call('run', '--approve-adapter', 'local').returncode, 2)

    def test_actual_interruption_and_resume(self):
        import time
        (self.root / 'worker.py').write_text("import json,sys,time; from pathlib import Path; json.load(sys.stdin); p=Path('started'); first=not p.exists(); p.write_text('started'); time.sleep(5 if first else 0); print('recovered')")
        self.contract['tasks'][0].update(timeout=8, max_attempts=2)
        self.save()
        proc = subprocess.Popen([sys.executable, '-m', 'harness.workflow_runner', 'run',
                                 str(self.root), '--approve-adapter', 'local'], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / 'started').exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((self.root / 'started').exists())
            self.assertEqual(self.call('run', '--approve-adapter', 'local').returncode, 2)
            proc.terminate()
            proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 130)
            self.assertEqual(json.loads(self.call('status').stdout)['tasks']['plan']['status'], 'running')
            resumed = self.call('resume', '--approve-adapter', 'local')
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            row = json.loads(resumed.stdout)['tasks']['plan']
            self.assertEqual(row['attempts'], 2)
            self.assertEqual(row['evidence'][0]['stdout'].strip(), 'recovered')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

    def test_retry_fail_then_pass(self):
        (self.root / 'worker.py').write_text("import json,sys; c=json.load(sys.stdin); print(c['attempt']); sys.exit(7 if c['attempt']==1 else 0)")
        self.contract['tasks'][0]['max_attempts'] = 2
        self.save()
        result = self.call('run', '--approve-adapter', 'local')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([e['result'] for e in json.loads(result.stdout)['tasks']['plan']['evidence']], ['FAIL', 'PASS'])

    def test_output_limit(self):
        (self.root / 'worker.py').write_text("print('x'*100000)")
        self.save()
        result = self.call('run', '--approve-adapter', 'local')
        self.assertEqual(result.returncode, 1, result.stderr)
        row = json.loads(result.stdout)['tasks']['plan']
        self.assertEqual(row['evidence'][0]['result'], 'OUTPUT_LIMIT')
        self.assertLessEqual(len(row['evidence'][0]['stdout']), 65536)

    def test_contract_mutation_during_execution_is_stale(self):
        (self.root / 'worker.py').write_text("from pathlib import Path; Path('workflow.json').write_text('{}')")
        self.save()
        result = self.call('run', '--approve-adapter', 'local')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('source', result.stderr)

    def test_four_roles_in_dependency_order(self):
        self.contract['tasks'] += [self.task('execute', deps=['plan']),
                                   self.task('review', role='reviewer', deps=['execute']),
                                   self.task('verify', role='verifier', deps=['review'])]
        self.save()
        planned = self.call('plan')
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertFalse((self.root / '.workflow').exists())
        result = self.call('run', '--approve-adapter', 'local')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)['tasks']
        self.assertEqual([r['evidence'][0]['stdout'].strip() for r in rows.values()],
                         ['planner', 'executor', 'reviewer', 'verifier'])
        self.assertEqual(self.call('resume').returncode, 0)
        self.assertEqual(json.loads(self.call('status').stdout)['tasks'], rows)

    def test_timeout_kills_descendants(self):
        import time
        child = "import time; from pathlib import Path; time.sleep(.5); Path('orphan-output').write_text('bad')"
        (self.root / 'worker.py').write_text("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(5)")
        self.contract['tasks'][0]['timeout'] = .1
        self.save()
        self.assertEqual(self.call('run', '--approve-adapter', 'local').returncode, 1)
        time.sleep(.6)
        self.assertFalse((self.root / 'orphan-output').exists())

    def test_exhausted_interrupted_attempt_is_failed_on_resume(self):
        self.assertEqual(self.call('run', '--approve-adapter', 'local').returncode, 0)
        path = self.root / '.workflow/state.json'
        state = json.loads(path.read_text())
        state['tasks']['plan'].update(status='running')
        path.write_text(json.dumps(state))
        result = self.call('resume')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)['tasks']['plan']['status'], 'failed')

    def test_real_adapter_and_checkpoint(self):
        result = self.call('run', '--approve-adapter', 'local')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual(state['tasks']['plan']['status'], 'passed')
        self.assertEqual(state['tasks']['plan']['evidence'][0]['stdout'].strip(), 'planner')
        self.assertEqual(json.loads(self.call('status').stdout), state)
        self.assertEqual(self.call('run', '--approve-adapter', 'local').returncode, 2)
        self.assertEqual(self.call('resume').returncode, 0)
