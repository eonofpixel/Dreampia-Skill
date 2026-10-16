import pathlib, tempfile, unittest
from unittest import mock
from harness import package_team

class PackageBoundariesTests(unittest.TestCase):
    def test_runtime_artifacts_are_not_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            for directory in ('harness','docs'):
                (root/directory).mkdir()
            (root/'harness/module.py').write_text('# source')
            (root/'docs/runbook.md').write_text('internal runbook')
            for directory in ('.next','test-results','playwright-report','.dreampia-workflow','.workflow','.local-data','node_modules'):
                p=root/'harness'/directory/'runtime.txt';p.parent.mkdir(parents=True);p.write_text('runtime')
            (root/'bin').mkdir();(root/'bin/dreampia.cjs').write_text('// shim')
            with mock.patch.object(package_team,'ROOT',root), mock.patch.object(package_team,'DIRECTORIES',('harness','docs')), mock.patch.object(package_team,'FILES',()):
                selected={p.relative_to(root).as_posix() for p in package_team.source_files()}
            self.assertEqual(selected,{'harness/module.py','docs/runbook.md','bin/dreampia.cjs'})
