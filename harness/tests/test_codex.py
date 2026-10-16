import json, pathlib, tempfile, unittest, sys, os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import core,codex_adapter
class CodexContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def fake(self,mode='success'):
        exe=self.root/'fake-codex'
        source='''#!EXE
import json,sys,time,pathlib
if '--version' in sys.argv:print('codex-cli 0.144.6');sys.exit()
if '--help' in sys.argv:print('--json --sandbox --ephemeral --ignore-user-config');sys.exit()
assert '--json' in sys.argv and '--sandbox' in sys.argv
assert '--ask-for-approval' in sys.argv and 'on-request' in sys.argv
assert not any('bypass' in x or x=='--yolo' for x in sys.argv)
prompt=sys.stdin.read();assert prompt
MODE
'''.replace('EXE',sys.executable)
        action={'success':"print(json.dumps({'type':'thread.started','thread_id':'fake'}));print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'FAKE_SECRET_OUTPUT'}}));print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}))",
                'auth':"print(json.dumps({'type':'turn.failed','error':{'message':'not logged in FAKE_SECRET_OUTPUT'}}));sys.exit(1)",
                'sleep':"time.sleep(10)", 'malformed':"print('not json')", 'noend':"print(json.dumps({'type':'turn.started'}))", 'approval':"print(json.dumps({'type':'error','message':'approval required'}));sys.exit(1)"}[mode]
        exe.write_text(source.replace('MODE',action));exe.chmod(0o700);return str(exe)
    def plan(self,exe,timeout=10):
        m={'version':1,'requirements':['R1'],'tasks':[{'id':'T1','requirements':['R1'],'adapter':{'kind':'codex','executable':exe,'prompt':'Implement only this task.'},'timeout':timeout,'checks':[{'id':'C1','argv':[sys.executable,'-c','pass']}]}]}
        (self.root/'harness.json').write_text(json.dumps(m))
    def test_malformed_protocol_rejected(self):
        self.assertEqual(codex_adapter.parse_events(b'not json')['category'],'PROTOCOL_ERROR')
    def test_no_terminal_not_success(self):
        self.assertNotEqual(codex_adapter.parse_events(b'{"type":"turn.started"}\n')['result'],'PASS')
    def test_failure_event_beats_exit_zero(self):
        self.assertEqual(codex_adapter.parse_events(b'{"type":"turn.failed","error":{"message":"oops"}}\n',0)['result'],'FAIL')
    def test_exit_failure_beats_complete(self):
        self.assertEqual(codex_adapter.parse_events(b'{"type":"turn.completed"}\n',1)['result'],'FAIL')
    def test_missing_binary_diagnostic(self):
        self.assertEqual(codex_adapter.probe('/does/not/exist')['category'],'NOT_INSTALLED')
    def test_no_provider_without_opt_in(self):
        self.plan(self.fake());q=core.run(self.root)['tasks']['T1']
        self.assertEqual(q['status'],'blocked');self.assertEqual(q['attempts'],0)
    def test_fake_provider_contract_integration(self):
        self.plan(self.fake());q=core.run(self.root,allow_provider=True)['tasks']['T1']
        self.assertEqual(q['status'],'verified');self.assertEqual(q['adapter_evidence']['category'],'SUCCESS')
        all_logs=''.join(p.read_text() for p in (self.root/'.harness').rglob('*') if p.is_file())
        self.assertNotIn('FAKE_SECRET_OUTPUT',all_logs)
    def test_auth_failure_no_automatic_retry(self):
        self.plan(self.fake('auth'));q=core.run(self.root,allow_provider=True)['tasks']['T1']
        self.assertEqual(q['status'],'failed');self.assertEqual(q['attempts'],1)
        self.assertEqual(q['adapter_evidence']['category'],'AUTH_REQUIRED')
    def test_approval_error_is_not_success(self):
        self.plan(self.fake('approval'));q=core.run(self.root,allow_provider=True)['tasks']['T1']
        self.assertEqual(q['adapter_evidence']['category'],'APPROVAL_REQUIRED')
    def test_provider_timeout(self):
        self.plan(self.fake('sleep'),timeout=.2);q=core.run(self.root,allow_provider=True)['tasks']['T1']
        self.assertEqual(q['adapter_evidence']['category'],'TIMEOUT')
    def test_provider_cancel_cleans_group(self):
        import subprocess,time
        exe=self.fake('sleep');source=pathlib.Path(exe).read_text()
        child="import time,pathlib;time.sleep(.7);pathlib.Path('child-survived').write_text('bad')"
        source=source.replace('time.sleep(10)',"import subprocess;subprocess.Popen([sys.executable,'-c',"+repr(child)+"]);pathlib.Path('.harness/provider-started').write_text('1');time.sleep(10)")
        pathlib.Path(exe).write_text(source);self.plan(exe,timeout=4)
        cli=str(pathlib.Path(core.__file__).with_name('cli.py'))
        diagnostic=tempfile.TemporaryFile()
        p=subprocess.Popen([sys.executable,cli,'run',str(self.root),'--allow-provider'],stdout=diagnostic,stderr=diagnostic)
        try:
            for _ in range(300):
                if (self.root/'.harness/provider-started').exists():break
                time.sleep(.01)
            self.assertTrue((self.root/'.harness/provider-started').exists())
            core.cancel(self.root);code=p.wait(timeout=5);diagnostic.seek(0)
            self.assertEqual(code,1,diagnostic.read().decode('utf-8',errors='replace'))
            q=core.status(self.root)['tasks']['T1'];self.assertEqual(q['adapter_evidence']['category'],'CANCELLED')
            time.sleep(.8);self.assertFalse((self.root/'child-survived').exists())
        finally:
            if p.poll() is None:p.kill();p.wait()
            diagnostic.close()
    def test_installed_cli_version_capability_probe(self):
        exe=self.fake();path=pathlib.Path(exe);path.write_text(path.read_text().replace('0.144.6','0.161.0'))
        self.assertEqual(codex_adapter.probe(exe)['category'],'READY')

    def test_unknown_cli_version_not_run(self):
        exe=self.fake();path=pathlib.Path(exe);path.write_text(path.read_text().replace('0.144.6','99.0.0'))
        self.assertEqual(codex_adapter.probe(exe)['category'],'UNVERIFIED_VERSION')
    def test_terminal_output_must_be_last(self):
        raw=b'{"type":"turn.completed"}\n{"type":"turn.started"}\n'
        self.assertEqual(codex_adapter.parse_events(raw)['category'],'PROTOCOL_ERROR')
