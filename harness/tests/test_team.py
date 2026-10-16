import contextlib, io, json, os, pathlib, shutil, sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import team_cli as team

class VerificationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        for name in ('web/package.json','web/app/page.tsx','web/app/admin/page.tsx','web/playwright.config.ts','web/tests/ui/smoke.spec.ts','web/lib/scoring.ts'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}' if name.endswith('package.json') else 'source')
        (self.root/'web/package.json').write_text(json.dumps({'scripts':{'build':'next build','test:unit':'node --test tests/unit/*.test.js','test:ui':'playwright test'}}))
    def tearDown(self):self.tmp.cleanup()
    def successful_run(self,cmd,**kwargs):
        import subprocess
        if cmd==['npm','run','test:ui']:
            p=pathlib.Path(kwargs['env']['DREAMPIA_UI_EVIDENCE'])/'flow.png';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        return subprocess.CompletedProcess(cmd,0,'executed','')
    def test_fresh_evidence_gates_reject_source_changes_and_tampering(self):
        (self.root/'web/node_modules').mkdir()
        (self.root/'docs').mkdir();(self.root/'docs/10_PROGRESS_HANDOFF.md').write_text('handoff')
        with patch('subprocess.run',side_effect=self.successful_run),patch.object(team,'doctor',return_value={'healthy':True}):
            team.app_check(self.root,True);team.ui_check(self.root,True)
            self.assertEqual(team.verify_gate(self.root,'before-claim-complete')['status'],'PASS')
            p=self.root/'evidence/app-check.json';e=json.loads(p.read_text())
            self.assertIn('source_fingerprint',e)
            for field,value in [('status','FAIL'),('checks',[]),('generated_at','2000-01-01T00:00:00Z')]:
                changed=dict(e);changed[field]=value;p.write_text(json.dumps(changed))
                self.assertEqual(team.verify_gate(self.root,'before-claim-complete')['status'],'FAIL')
            p.write_text(json.dumps(e))
            (self.root/'web/app/page.tsx').write_text('changed')
            self.assertEqual(team.verify_gate(self.root,'before-claim-complete')['status'],'FAIL')
            self.assertEqual(team.verify_gate(self.root,'ui-evidence')['status'],'FAIL')
    def test_old_screenshots_cannot_satisfy_new_run(self):
        (self.root/'web/node_modules').mkdir()
        import subprocess
        with patch('subprocess.run',side_effect=self.successful_run):
            first=team.ui_check(self.root,True)
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,'','')):
            second=team.ui_check(self.root,True)
        self.assertEqual(first['status'],'PASS');self.assertEqual(second['status'],'FAIL')
        self.assertEqual(second['screenshots'],[])
    def test_placeholder_unit_script_cannot_pass(self):
        (self.root/'web/node_modules').mkdir()
        (self.root/'web/package.json').write_text(json.dumps({'scripts':{'test:unit':'node -e "console.log(\'unit tests TODO\')"'}}))
        with patch('subprocess.run',side_effect=self.successful_run):
            self.assertEqual(team.app_check(self.root,True)['status'],'FAIL')

    def test_export_requires_explicit_allowlist_and_hides_internal_paths(self):
        (self.root/'docs/internal').mkdir(parents=True)
        for name,text in {'public.md':'---\nclient_export_allowed: true\n---\nPublic', 'unreviewed.md':'Draft', 'internal/strategy.md':'---\nclient_export_allowed: true\nvisibility: internal_only\n---\nSecret method'}.items():
            (self.root/'docs'/name).write_text(text)
        result=team.export_client_summary(self.root)
        text=(self.root/result['output']).read_text()
        self.assertIn('docs/public.md',text);self.assertNotIn('unreviewed.md',text);self.assertNotIn('strategy.md',text)
        self.assertEqual(result['included'],['docs/public.md'])
    def test_package_excludes_unapproved_files_internal_paths_and_old_zips(self):
        import zipfile
        (self.root/'client/internal').mkdir(parents=True)
        (self.root/'client/public.md').write_text('---\nclient_export_allowed: true\n---\nReviewed')
        (self.root/'client/internal/strategy.md').write_text('---\nclient_export_allowed: true\n---\nPrivate')
        (self.root/'client/raw.txt').write_text('unapproved')
        with zipfile.ZipFile(self.root/'client/old.zip','w') as z:z.writestr('secret.txt','hidden')
        result=team.package_client(self.root,'safe.zip')
        self.assertEqual(result['included'],['client/public.md'])
        with zipfile.ZipFile(self.root/result['output']) as z:self.assertEqual(z.namelist(),['client/public.md'])
    def test_allowlisted_secret_blocks_export_and_package_without_writes(self):
        (self.root/'docs').mkdir()
        p=self.root/'docs/approved.md'
        for secret in ('API_KEY=FAKE_SECRET_DO_NOT_COPY','-----BEGIN PRIVATE KEY-----','Bearer abcdefghijklmnopqrstuvwxyz123456','password: "hunter2"'):
            p.write_text('---\nclient_export_allowed: true\n---\n'+secret)
            with self.assertRaises(team.InstallError):team.export_client_summary(self.root)
            with self.assertRaises(team.InstallError):team.package_client(self.root,'safe.zip')
            self.assertFalse((self.root/'client/CLIENT_SAFE_SUMMARY.md').exists())
            self.assertFalse((self.root/'client/safe.zip').exists())
    def test_client_gate_rejects_secrets_and_nested_archives(self):
        import zipfile
        (self.root/'docs').mkdir();(self.root/'docs/readme.md').write_text('docs')
        (self.root/'client').mkdir();p=self.root/'client/public.md'
        with patch.object(team,'doctor',return_value={'healthy':True}):
            p.write_text('---\nclient_export_allowed: true\n---\nAPI_KEY=FAKE_SECRET')
            self.assertEqual(team.verify_gate(self.root,'before-client-send')['status'],'FAIL')
            p.write_text('---\nclient_export_allowed: true\n---\nReviewed')
            with zipfile.ZipFile(self.root/'client/bad.zip','w') as z:z.writestr('internal/strategy.md','private')
            self.assertEqual(team.verify_gate(self.root,'before-client-send')['status'],'FAIL')

    def test_client_symlink_is_not_silently_accepted(self):
        (self.root/'client').mkdir();(self.root/'docs').mkdir()
        (self.root/'docs/public.md').write_text('---\nclient_export_allowed: true\n---\nPublic')
        team.export_client_summary(self.root)
        (self.root/'client/leak.md').symlink_to(self.root/'web/package.json')
        with self.assertRaises(team.InstallError):team.package_client(self.root,'safe.zip')
        with patch.object(team,'doctor',return_value={'healthy':True}),contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(team.main(['verify','--project',str(self.root),'--gate','before-client-send']),0)
    def test_evidence_checks_and_screenshot_hashes_are_required(self):
        (self.root/'web/node_modules').mkdir()
        with patch('subprocess.run',side_effect=self.successful_run):team.ui_check(self.root,True)
        p=self.root/'evidence/ui-check.json';original=json.loads(p.read_text())
        self.assertTrue(team.evidence_valid(self.root,'ui'))
        for field,value in [('checks',[{'name':'npm run test:ui','status':'PASS'}]),('source_fingerprint','0'*64),('generated_at','2999-01-01T00:00:00Z'),('screenshots',[])]:
            e=dict(original);e[field]=value;p.write_text(json.dumps(e))
            self.assertFalse(team.evidence_valid(self.root,'ui'))
        p.write_text(json.dumps(original))
        (self.root/original['screenshots'][0]).write_bytes(b'\x89PNG\r\n\x1a\nchanged')
        self.assertFalse(team.evidence_valid(self.root,'ui'))
    def test_source_change_during_execution_fails_closed(self):
        (self.root/'web/node_modules').mkdir()
        def changed_run(cmd,**kwargs):
            (self.root/'web/app/page.tsx').write_text((self.root/'web/app/page.tsx').read_text()+'changed')
            return self.successful_run(cmd,**kwargs)
        with patch('subprocess.run',side_effect=changed_run):
            self.assertEqual(team.app_check(self.root,True)['status'],'FAIL')
            self.assertEqual(team.ui_check(self.root,True)['status'],'FAIL')

    @unittest.skipUnless(shutil.which('npm') and shutil.which('node'),'Node/npm unavailable')
    def test_real_npm_execution_and_failing_unit_exit(self):
        (self.root/'web/node_modules').mkdir()
        unit=self.root/'web/tests/unit/pass.test.cjs';unit.parent.mkdir(parents=True,exist_ok=True)
        unit.write_text("const test = require('node:test'); const assert = require('node:assert/strict'); test('real harness fixture', () => assert.equal(2, 2));")
        p=self.root/'web/package.json';p.write_text(json.dumps({'scripts':{'build':'node --check tests/unit/pass.test.cjs','test:unit':'node --test tests/unit/pass.test.cjs'}}))
        result=team.app_check(self.root,True)
        self.assertEqual(result['status'],'PASS');self.assertTrue(team.evidence_valid(self.root,'app'))
        unit.write_text(unit.read_text().replace('assert.equal(2, 2)','assert.equal(2, 3)'))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(team.main(['app-check','--project',str(self.root),'--apply']),1)
        e=json.loads((self.root/'evidence/app-check.json').read_text())
        self.assertEqual(next(c['status'] for c in e['checks'] if c['name']=='npm run test:unit'),'FAIL')

    def test_not_run_is_not_pass_and_cli_is_nonzero(self):
        for action in ('app-check','ui-check'):
            result=getattr(team,action.replace('-','_'))(self.root,True)
            self.assertEqual(result['status'],'FAIL')
            self.assertTrue(any(c['status']=='NOT_RUN' for c in result['checks']))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(team.main([action,'--project',str(self.root),'--apply']),1)


class TeamInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)/'project';self.root.mkdir()
    def tearDown(self):self.tmp.cleanup()
    def init(self):return team.install(self.root,'init',True)
    def test_preview_no_mutation_and_install_manifest_hashes(self):
        plan=team.install(self.root,'init');self.assertTrue(plan['changes']);self.assertEqual(list(self.root.iterdir()),[])
        self.init();self.assertTrue(team.doctor(self.root)['healthy'])
        m=team.load_manifest(self.root)
        for name,sha in m['files'].items():self.assertEqual(team.sha((self.root/name).read_bytes()),sha)
    def test_reinstall_idempotent(self):
        self.init();rollback=(self.root/team.META/'rollback.json').read_bytes()
        result=self.init();self.assertEqual(result['changes'],[]);self.assertEqual((self.root/team.META/'rollback.json').read_bytes(),rollback)
    def test_preexisting_collision_preserved(self):
        p=self.root/'.agents/skills/ai-dev-execution/SKILL.md';p.parent.mkdir(parents=True);p.write_text('user content')
        with self.assertRaises(team.Conflict):self.init()
        self.assertEqual(p.read_text(),'user content');self.assertFalse((self.root/team.META).exists())
    def test_modified_managed_file_blocks_update_uninstall(self):
        self.init();p=self.root/'.dreampia/WORK_CONTRACT.ko.md';p.write_text('USER CHANGE')
        for action in ('update','uninstall'):
            with self.assertRaises(team.Conflict):team.install(self.root,action,True)
        self.assertEqual(p.read_text(),'USER CHANGE');self.assertFalse(team.doctor(self.root)['healthy'])
    def test_update_and_rollback_restores_exact_files(self):
        self.init();before=(self.root/'.dreampia/WORK_CONTRACT.ko.md').read_bytes();old=team.load_manifest(self.root)
        source=pathlib.Path(self.tmp.name)/'source';shutil.copytree(team.PACKAGE,source,ignore=shutil.ignore_patterns('evidence','__pycache__'))
        (source/'team/WORK_CONTRACT.ko.md').write_text('NEW CONTRACT')
        self.assertTrue(team.install(self.root,'update',False,source)['changes']);team.install(self.root,'update',True,source)
        self.assertEqual((self.root/'.dreampia/WORK_CONTRACT.ko.md').read_text(),'NEW CONTRACT')
        self.assertTrue(team.rollback(self.root)['changes']);team.rollback(self.root,True)
        self.assertEqual(team.load_manifest(self.root),old);self.assertEqual((self.root/'.dreampia/WORK_CONTRACT.ko.md').read_bytes(),before)
    def test_uninstall_only_managed_files_and_rollback(self):
        self.init();user=self.root/'.dreampia/user.txt';user.write_text('user');agent=self.root/'AGENTS.md';agent.write_text('original')
        names=list(team.load_manifest(self.root)['files']);team.install(self.root,'uninstall',True)
        self.assertTrue(all(not (self.root/name).exists() for name in names));self.assertEqual(user.read_text(),'user');self.assertEqual(agent.read_text(),'original')
        team.rollback(self.root,True);self.assertTrue(team.doctor(self.root)['healthy'])
    def test_config_typo_and_bool_policy_rejected(self):
        self.init();p=self.root/'.dreampia/project.json';m=json.loads(p.read_text());m['provider_enable']=True;p.write_text(json.dumps(m))
        with self.assertRaises(team.InstallError):team.doctor(self.root)
        m=json.loads((team.PACKAGE/'team/policy.json').read_text());m['executor_count']=True
        with self.assertRaises(team.InstallError):team.validate_policy(m)
    def test_symlink_escape_and_manifest_tamper_rejected(self):
        outside=pathlib.Path(self.tmp.name)/'outside';outside.mkdir();(self.root/'.agents').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(team.InstallError):self.init()
        self.assertEqual(list(outside.iterdir()),[])
        (self.root/'.agents').unlink();self.init();p=self.root/team.META/'manifest.json';m=json.loads(p.read_text());m['files']['../outside/sensitive']='0'*64;p.write_text(json.dumps(m))
        with self.assertRaises(team.InstallError):team.install(self.root,'uninstall',True)
    def test_rollback_preserves_changed_file(self):
        self.init();p=self.root/'.dreampia/project.json';p.write_text('user')
        with self.assertRaises(team.Conflict):team.rollback(self.root,True)
        self.assertEqual(p.read_text(),'user')
    def test_partial_transaction_explicit_rollback_no_replay(self):
        original=team.write_bytes;failed=[False]
        def fail(root,name,data):
            if name=='.dreampia/team.json' and not failed[0]:failed[0]=True;raise OSError('injected write failure')
            return original(root,name,data)
        with patch.object(team,'write_bytes',side_effect=fail):
            with self.assertRaises(OSError):self.init()
        with self.assertRaises(team.Conflict):team.install(self.root,'init',True)
        self.assertTrue(team.rollback(self.root)['recovering_partial']);team.rollback(self.root,True)
        self.assertIsNone(team.load_manifest(self.root));self.assertFalse((self.root/'.agents/skills/ai-dev-execution/SKILL.md').exists())
        self.init();self.assertTrue(team.doctor(self.root)['healthy'])
    def test_secrets_excluded_from_manifest_backup_and_logs(self):
        (self.root/'.env').write_text('API_KEY=FAKE_SECRET_DO_NOT_COPY')
        self.init();team.install(self.root,'update',True)
        contents=''.join(p.read_text() for p in (self.root/team.META).rglob('*') if p.is_file())
        self.assertNotIn('FAKE_SECRET_DO_NOT_COPY',contents)
        self.assertNotIn('.env',team.load_manifest(self.root)['files'])
    def test_unknown_cli_option_is_closed(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):team.main(['init','--project',str(self.root),'--aply'])
        self.assertEqual(list(self.root.iterdir()),[])
    def test_interrupted_rollback_can_recover_then_retry(self):
        self.init();source=pathlib.Path(self.tmp.name)/'new';shutil.copytree(team.PACKAGE,source,ignore=shutil.ignore_patterns('evidence','__pycache__'))
        (source/'team/WORK_CONTRACT.ko.md').write_text('updated work');(source/'adapters/codex.ko.md').write_text('updated host')
        team.install(self.root,'update',True,source);updated=team.load_manifest(self.root)
        original=team.write_bytes;count=[0]
        def fail(root,name,data):
            if name.startswith('.dreampia/'):
                count[0]+=1
                if count[0]==2:raise OSError('injected interrupted rollback')
            return original(root,name,data)
        with patch.object(team,'write_bytes',side_effect=fail):
            with self.assertRaises(OSError):team.rollback(self.root,True)
        team.rollback(self.root,True)
        # Recovery aborts the interrupted rollback, preserving the previous committed update.
        self.assertEqual(team.load_manifest(self.root),updated)
        self.assertTrue(team.doctor(self.root)['healthy'])
        team.rollback(self.root,True)
        self.assertEqual((self.root/'.dreampia/WORK_CONTRACT.ko.md').read_bytes(),(team.PACKAGE/'team/WORK_CONTRACT.ko.md').read_bytes())


    def test_scaffold_verify_and_client_export(self):
        self.init()
        preview=team.project_scaffold(self.root,'assessment-service',False)
        self.assertTrue(preview['changes']);self.assertFalse((self.root/'docs/ASSESSMENT_PRD.md').exists())
        applied=team.project_scaffold(self.root,'assessment-service',True)
        self.assertTrue(applied['applied']);self.assertTrue((self.root/'docs/ASSESSMENT_PRD.md').is_file())
        self.assertEqual(team.verify_gate(self.root,'before-dev-start')['status'],'PASS')
        exported=team.export_client_summary(self.root,'client')
        self.assertTrue((self.root/exported['output']).is_file())
        self.assertEqual(team.verify_gate(self.root,'before-client-send')['status'],'PASS')
        with self.assertRaises(team.InstallError):team.project_scaffold(self.root,'unknown',False)

    def test_scaffold_preserves_existing_files(self):
        self.init();(self.root/'docs').mkdir();(self.root/'docs/ASSESSMENT_PRD.md').write_text('user')
        plan=team.project_scaffold(self.root,'assessment-service',True)
        self.assertIn('docs/ASSESSMENT_PRD.md',plan['conflicts'])
        self.assertEqual((self.root/'docs/ASSESSMENT_PRD.md').read_text(),'user')


    def test_app_scaffold_slice_and_client_package(self):
        self.init();team.project_scaffold(self.root,'assessment-service',True)
        preview=team.scaffold_app(self.root,'next-assessment-app',False)
        self.assertTrue(preview['changes']);self.assertFalse((self.root/'web/app/page.tsx').exists())
        applied=team.scaffold_app(self.root,'next-assessment-app',True)
        self.assertTrue(applied['applied']);self.assertTrue((self.root/'web/app/page.tsx').is_file())
        slice_plan=team.plan_slice(self.root,'student-submit-flow',True)
        self.assertTrue(slice_plan['applied']);self.assertTrue((self.root/'.dreampia/generated/slices/student-submit-flow.md').is_file())
        team.export_client_summary(self.root,'client')
        pkg=team.package_client(self.root,'client-package.zip')
        self.assertTrue((self.root/pkg['output']).is_file())
        self.assertTrue(pkg['included'])
        self.assertTrue(any(x.endswith('CLIENT_SAFE_SUMMARY.md') for x in pkg['included']))
        with self.assertRaises(team.InstallError):team.scaffold_app(self.root,'unknown',False)

    def test_client_package_rejects_unsafe_output_name(self):
        self.init()
        with self.assertRaises(team.InstallError):team.package_client(self.root,'../bad.zip')


    def test_app_check_static_and_evidence(self):
        self.init();team.scaffold_app(self.root,'next-assessment-app',True)
        self.assertEqual(team.verify_gate(self.root,'app-static')['status'],'PASS')
        preview=team.app_check(self.root,False)
        self.assertEqual(preview['status'],'PASS');self.assertFalse((self.root/'evidence/app-check.json').exists())
        applied=team.app_check(self.root,True)
        self.assertTrue((self.root/'evidence/app-check.json').is_file())
        self.assertIn(applied['status'],('PASS','FAIL'))
        self.assertEqual(team.verify_gate(self.root,'before-claim-complete')['status'],'FAIL')


    def test_ui_check_static_and_evidence(self):
        self.init();team.scaffold_app(self.root,'next-assessment-app',True)
        self.assertEqual(team.verify_gate(self.root,'app-static')['status'],'PASS')
        preview=team.ui_check(self.root,False)
        self.assertEqual(preview['status'],'PASS')
        applied=team.ui_check(self.root,True)
        self.assertTrue((self.root/'evidence/ui-check.json').is_file())
        self.assertIn(applied['status'],('PASS','FAIL'))
        self.assertEqual(team.verify_gate(self.root,'ui-evidence')['status'],'FAIL')
