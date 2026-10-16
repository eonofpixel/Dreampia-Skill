import pathlib, subprocess, unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
class WorkflowCLIIntegrationTests(unittest.TestCase):
    def test_node_shim_routes_workflow_help(self):
        p=subprocess.run(['node',str(ROOT/'bin/dreampia.cjs'),'workflow','--help'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('resume',p.stdout)
        self.assertIn('--approve-adapter',p.stdout)
