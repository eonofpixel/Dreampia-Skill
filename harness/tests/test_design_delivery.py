"""Distribution/lifecycle regressions; does not score design instructions."""
import json,pathlib,shutil,sys,tempfile,unittest,zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import package_team,skill_bundle,team_cli as team

class DesignDeliveryTests(unittest.TestCase):
    def test_reference_growth_update_rollback_preserves_user_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=pathlib.Path(tmp);root=base/'project';root.mkdir();(root/'AGENTS.md').write_text('USER')
            # Old-shaped payload, not a claim about a real previous-version install.
            old=base/'old';shutil.copytree(team.PACKAGE,old,ignore=shutil.ignore_patterns('evidence','__pycache__'))
            refs=['references/design-web.md', 'references/design-desktop.md', 'references/design-mobile.md', 'references/design-verification.md']
            for name in refs:(old/'ai-dev-execution'/name).unlink()
            (old/'ai-dev-execution/SKILL.md').write_text('---\nname: ai-dev-execution\ndescription: previous fixture\n---\nprevious entry\n')
            skill_bundle.write(old/'ai-dev-execution',team.VERSION)
            team.install(root,'init',True,old);before=team.load_manifest(root);skill=root/'.agents/skills/ai-dev-execution'
            preview=team.install(root,'update',False);self.assertTrue(preview['changes']);self.assertEqual(team.load_manifest(root),before)
            self.assertTrue(all(not (skill/n).exists() for n in refs))
            team.install(root,'update',True)
            for n in refs:self.assertEqual((skill/n).read_bytes(),(team.PACKAGE/'ai-dev-execution'/n).read_bytes())
            self.assertTrue(team.doctor(root)['healthy']);updated=team.load_manifest(root)
            (skill/refs[0]).write_text('USER EDIT')
            with self.assertRaises(team.Conflict):team.rollback(root,True)
            self.assertEqual((skill/refs[0]).read_text(),'USER EDIT')
            (skill/refs[0]).write_bytes((team.PACKAGE/'ai-dev-execution'/refs[0]).read_bytes())
            team.rollback(root,True);self.assertEqual(team.load_manifest(root),before);self.assertTrue(all(not (skill/n).exists() for n in refs));self.assertEqual((root/'AGENTS.md').read_text(),'USER')

    def test_explicit_npm_list_and_both_zips_include_reference_bytes(self):
        refs=['ai-dev-execution/references/design-web.md', 'ai-dev-execution/references/design-desktop.md', 'ai-dev-execution/references/design-mobile.md', 'ai-dev-execution/references/design-verification.md']
        files=json.loads((team.PACKAGE/'package.json').read_text())['files']
        for n in refs:self.assertIn(n,files)
        with tempfile.TemporaryDirectory() as tmp:
            for only in (True,False):
                dest=pathlib.Path(tmp)/('skill.zip' if only else 'team.zip');package_team.build(dest,only)
                with zipfile.ZipFile(dest) as z:
                    for n in refs:self.assertEqual(z.read(n if only else 'dreampia-skill/'+n),(team.PACKAGE/n).read_bytes())
