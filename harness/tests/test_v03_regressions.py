import json, os, pathlib, subprocess, sys, tempfile, time, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import core, codex_adapter, eval_runner
import test_product
ROOT = pathlib.Path(__file__).resolve().parents[2]

class AuditRegressionTests(unittest.TestCase):
    def test_manifest_typo_rejected_before_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            m = {'version':1, 'requirements':['R1'], 'tasks':[{'id':'T1', 'requirements':['R1'], 'max_attempt':1,
                 'adapter':{'kind':'command', 'argv':[sys.executable,'-c',"from pathlib import Path;p=Path('counter');p.write_text(str(int(p.read_text())+1) if p.exists() else '1');raise SystemExit(1)"]},
                 'checks':[{'id':'C1','argv':[sys.executable,'-c','pass']}]}]}
            (root/'harness.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError): core.run(root)
            self.assertFalse((root/'counter').exists())

    def test_eval_infinite_budget_rejected(self):
        fixture = test_product.ProductTests(); fixture.setUp()
        try:
            out, data = fixture.audited()
            for r in data['records']: r['controls']['time_budget_seconds'] = float('inf')
            (out/'results.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError): eval_runner.aggregate(ROOT/'evals/suite.json',out/'results.json')
        finally: fixture.tearDown()

    def test_probe_timeout_cleans_resistant_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); marker=root/'survived'; pidfile=root/'child.pid'; gate=root/'released'; exe=root/'fake-codex'
            child = "import signal,time,pathlib,os;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path(%r).write_text(str(os.getpid()))\nwhile not pathlib.Path(%r).exists():time.sleep(.01)\npathlib.Path(%r).write_text('bad');time.sleep(10)" % (str(pidfile),str(gate),str(marker))
            exe.write_text('#!'+sys.executable+'\nimport subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",'+repr(child)+'])\ntime.sleep(10)\n');exe.chmod(0o700)
            try:
                self.assertEqual(codex_adapter.probe(str(exe),timeout=3)['category'],'PROBE_TIMEOUT')
                self.assertTrue(pidfile.exists(), "fixture child did not start")
                gate.write_text("probe returned")
                time.sleep(.5)
                self.assertFalse(marker.exists(), 'probe descendant survived timeout')
            finally:
                if pidfile.exists():
                    try: os.kill(int(pidfile.read_text()),9)
                    except OSError: pass
