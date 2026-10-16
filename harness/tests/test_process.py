import json, os, pathlib, signal, subprocess, sys, tempfile, time, unittest
CLI=pathlib.Path(__file__).resolve().parents[1]/'cli.py'

class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.tmp.name); self.processes=[]
    def tearDown(self):
        for p in self.processes:
            if p.poll() is None: p.kill(); p.wait()
        self.tmp.cleanup()
    def plan(self,adapter=None,timeout=10):
        m={'version':1,'requirements':['R1'],'tasks':[{'id':'T1','requirements':['R1'],'depends_on':[], 'adapter':adapter or {'kind':'deterministic','delay':1},'max_attempts':3,'timeout':timeout,'checks':[{'id':'C1','argv':[sys.executable,'-c','pass']}]}]}
        (self.root/'harness.json').write_text(json.dumps(m))
    def start(self):
        p=subprocess.Popen([sys.executable,str(CLI),'run',str(self.root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); self.processes.append(p); return p
    def call(self,action): return subprocess.run([sys.executable,str(CLI),action,str(self.root)],capture_output=True,text=True,timeout=10)
    def wait_running(self):
        for _ in range(200):
            try:
                if json.loads((self.root/'.harness/state.json').read_text())['tasks']['T1']['status']=='running': return
            except (FileNotFoundError,json.JSONDecodeError): pass
            time.sleep(.01)
        self.fail('runner never started')
    def test_duplicate_process(self):
        self.plan(); p=self.start(); self.wait_running()
        self.assertEqual(self.call('run').returncode,2)
        self.assertEqual(p.wait(timeout=5),0)
    def test_cancel_and_resume(self):
        self.plan(); p=self.start(); self.wait_running(); self.assertEqual(self.call('cancel').returncode,0)
        self.assertEqual(p.wait(timeout=5),1)
        q=json.loads(self.call('status').stdout)['tasks']['T1']; self.assertEqual(q['status'],'cancelled')
        r=self.call('run'); self.assertEqual(r.returncode,0,r.stderr)
    def test_sigterm_and_resume(self):
        self.plan(); p=self.start(); self.wait_running(); p.send_signal(signal.SIGTERM)
        self.assertEqual(p.wait(timeout=5),1); self.assertEqual(self.call('run').returncode,0)
    def test_kill_restart(self):
        self.plan(); p=self.start(); self.wait_running(); p.kill(); p.wait()
        r=self.call('run'); self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['tasks']['T1']['attempts'],2)
    def test_command_adapter_contract(self):
        script="import json,sys,pathlib; c=json.load(sys.stdin); assert c['protocol']==1; assert c['idempotency_key']; pathlib.Path('produced.txt').write_text(c['task']['id'])"
        self.plan({'kind':'command','argv':[sys.executable,'-c',script]})
        self.assertEqual(self.call('run').returncode,0)
        self.assertEqual((self.root/'produced.txt').read_text(),'T1')
    def test_command_timeout(self):
        self.plan({'kind':'command','argv':[sys.executable,'-c','import time; time.sleep(30)']},timeout=.1)
        r=self.call('run'); self.assertEqual(r.returncode,1)
        self.assertEqual(json.loads(r.stdout)['tasks']['T1']['attempts'],3)
    def test_orphan_holds_lock_after_runner_kill(self):
        # Hold the orphan alive until the contender has actually checked the lock.
        script="import pathlib,time; pathlib.Path('.harness/started').write_text('1'); deadline=time.monotonic()+20\nwhile not pathlib.Path('.harness/release').exists() and time.monotonic()<deadline: time.sleep(.01)"
        self.plan({'kind':'command','argv':[sys.executable,'-c',script]})
        p=self.start()
        for _ in range(500):
            if (self.root/'.harness/started').exists(): break
            time.sleep(.01)
        self.assertTrue((self.root/'.harness/started').exists()); p.kill(); p.wait()
        try:
            self.assertEqual(self.call('run').returncode,2)
        finally:
            (self.root/'.harness/release').write_text('release after contention check')
        import process
        released=False
        for _ in range(500):
            try:
                fd=process.acquire_lock(self.root/'.harness/lock')
                process.release_lock(fd);released=True;break
            except BlockingIOError:time.sleep(.01)
        self.assertTrue(released,'orphan did not release lock')
        self.assertEqual(self.call('run').returncode,0)
    def child_command(self):
        child="import time,pathlib; time.sleep(.7); pathlib.Path('child-survived.txt').write_text('bad')"
        parent="import subprocess,sys,time,pathlib; subprocess.Popen([sys.executable,'-c',"+repr(child)+"]); pathlib.Path('.harness/child-started').write_text('1'); time.sleep(10)"
        return {'kind':'command','argv':[sys.executable,'-c',parent]}
    def test_timeout_kills_child_group(self):
        self.plan(self.child_command(),timeout=.15)
        r=self.call('run'); self.assertEqual(r.returncode,1)
        time.sleep(.8)
        self.assertFalse((self.root/'child-survived.txt').exists())
    def test_cancel_kills_child_group(self):
        self.plan(self.child_command()); p=self.start()
        for _ in range(200):
            if (self.root/'.harness/child-started').exists(): break
            time.sleep(.01)
        self.assertTrue((self.root/'.harness/child-started').exists())
        self.assertEqual(self.call('cancel').returncode,0); self.assertEqual(p.wait(timeout=5),1)
        time.sleep(.8); self.assertFalse((self.root/'child-survived.txt').exists())
    def test_invalid_top_level_sanitized(self):
        (self.root/'harness.json').write_text('[]')
        r=self.call('validate'); self.assertEqual(r.returncode,2)
        self.assertNotIn('Traceback',r.stderr)
