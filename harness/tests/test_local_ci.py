import contextlib, io, os, pathlib, signal, subprocess, sys, tempfile, time, unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import local_ci

class LocalCITests(unittest.TestCase):
    def checks(self,commands,timeout=5,stopped=lambda:False):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return local_ci.run_checks(commands,os.environ.copy(),timeout,stopped)
    def test_real_failure_is_not_success_and_cwd_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.checks([([sys.executable,'-c',"from pathlib import Path;Path('proof').write_text('yes')"],tmp),([sys.executable,'-c','raise SystemExit(3)'],tmp)])
            self.assertEqual([r['result'] for r in rows],['PASS','FAIL'])
            self.assertEqual(rows[1]['exit'],3);self.assertTrue((pathlib.Path(tmp)/'proof').exists())
    def test_timeout_cleans_children_and_records_remaining_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            child="import signal,time,pathlib;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path('started').write_text('yes');time.sleep(2);pathlib.Path('survived').write_text('bad')"
            parent="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"+repr(child)+"]);time.sleep(30)"
            rows=self.checks([([sys.executable,'-c',parent],tmp),([sys.executable,'-c',"from pathlib import Path;Path('unexpected').touch()"],tmp)],1.5)
            self.assertTrue((pathlib.Path(tmp)/'started').exists())
            self.assertEqual([r['result'] for r in rows],['TIMEOUT','NOT_RUN']);time.sleep(.8)
            self.assertFalse((pathlib.Path(tmp)/'survived').exists());self.assertFalse((pathlib.Path(tmp)/'unexpected').exists())
    def test_missing_command_and_pre_cancel_are_not_pass(self):
        rows=self.checks([(['/not-a-dreampia-executable'],'.')]);self.assertEqual(rows[0]['result'],'NOT_RUN')
        rows=self.checks([([sys.executable,'-c','raise SystemExit(99)'],'.')],stopped=lambda:True);self.assertEqual(rows[0]['result'],'NOT_RUN')
    def test_main_timeout_has_summary_and_source_change_is_stale(self):
        for before,after,reason,expected in [('a','a','TIMEOUT','FAIL'),('a','b',None,'STALE')]:
            out=io.StringIO()
            result={'reason':reason,'exit_code':None if reason else 0,'stdout':b'','stderr':b''}
            with mock.patch.object(local_ci,'source_digest',side_effect=[before,after]),mock.patch.object(local_ci.process,'capture',return_value=result),contextlib.redirect_stdout(out):
                self.assertEqual(local_ci.main(),1)
            import json
            final=json.loads(out.getvalue().splitlines()[-1]);self.assertFalse(final['all_pass']);self.assertEqual(final['status'],expected)
    def test_main_signal_cancels_only_its_fixture_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            child="import signal,time,pathlib;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path('started').touch();time.sleep(2);pathlib.Path('survived').touch()"
            parent="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"+repr(child)+"]);time.sleep(30)"
            commands=[([sys.executable,'-c',parent],tmp),([sys.executable,'-c','pass'],tmp)]
            script="import sys;sys.path.insert(0,"+repr(str(pathlib.Path(local_ci.__file__).parent))+ ");import local_ci;local_ci.source_digest=lambda:'fixture';run=local_ci.run_checks;local_ci.run_checks=lambda commands,env,**kw:run("+repr(commands)+",env,**kw);raise SystemExit(local_ci.main())"
            p=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                end=time.monotonic()+5
                while not (pathlib.Path(tmp)/'started').exists() and time.monotonic()<end:time.sleep(.01)
                self.assertTrue((pathlib.Path(tmp)/'started').exists());p.send_signal(signal.SIGTERM)
                out,err=p.communicate(timeout=5);self.assertEqual(p.returncode,1,err)
                import json
                rows=[json.loads(x) for x in out.splitlines()];self.assertEqual([x['result'] for x in rows[:-1]],['CANCELLED','NOT_RUN']);self.assertFalse(rows[-1]['all_pass'])
                time.sleep(2);self.assertFalse((pathlib.Path(tmp)/'survived').exists())
            finally:
                if p.poll() is None:p.terminate();p.communicate(timeout=5)
