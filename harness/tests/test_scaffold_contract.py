import json, pathlib, re, unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
SCAFFOLD=ROOT/'ai-dev-execution/assets/scaffolds/next-assessment-app'

class ReproducibleScaffoldTests(unittest.TestCase):
    def test_generated_gitignore_uses_nonhidden_template(self):
        from harness.team_cli import scaffold_app_files
        files=scaffold_app_files('next-assessment-app')
        self.assertIn('web/.gitignore', files)
        self.assertNotIn('web/gitignore.template', files)
        self.assertTrue((SCAFFOLD/'gitignore.template').is_file())

    def test_dependencies_are_pinned(self):
        pkg=json.loads((SCAFFOLD/'package.json').read_text())
        for group in ('dependencies','devDependencies'):
            for name,version in pkg.get(group,{}).items():
                with self.subTest(name=name):
                    self.assertRegex(version,r'^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$')
    def test_lockfile_matches_manifest(self):
        pkg=json.loads((SCAFFOLD/'package.json').read_text())
        lock=json.loads((SCAFFOLD/'package-lock.json').read_text())
        self.assertGreaterEqual(lock['lockfileVersion'],2)
        for group in ('dependencies','devDependencies'):
            self.assertEqual(lock['packages'][''].get(group,{}),pkg.get(group,{}))
    def test_unit_script_is_not_placeholder(self):
        script=json.loads((SCAFFOLD/'package.json').read_text())['scripts']['test:unit']
        self.assertNotRegex(script.lower(),r'todo|console\.log|passwithnotests')
        self.assertTrue(any((SCAFFOLD/'tests/unit').glob('*test*')), 'real unit test file required')
