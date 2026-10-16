import unittest,tempfile,pathlib,hashlib,copy,json
from harness.handoff_contract import validate
class HandoffTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name);(self.root/'proof.log').write_text('actual test output')
  self.contract={'task_id':'T1','from_role':'executor','to_role':'verifier','scope':'local-prototype','owned_paths':['web'],'constraints':['no deployment'],'unresolved':[],'acceptance':[{'id':'A1','kind':'behavior','status':'PASS','evidence':[{'path':'proof.log','sha256':hashlib.sha256((self.root/'proof.log').read_bytes()).hexdigest(),'kind':'test-log','status':'PASS','exit_code':0}]}]}
 def test_appearance_without_screenshot(self):
  self.contract['acceptance'][0]['kind']='appearance'
  with self.assertRaises(ValueError):validate(self.contract,self.root)
 def test_unresolved_blocks(self):
  self.contract['unresolved']=['approval pending'];self.assertFalse(validate(self.contract,self.root)['ready'])
 def test_valid(self):self.assertTrue(validate(self.contract,self.root)['ready'])
 def test_unrun_blocks(self):
  a=self.contract['acceptance'][0];a.update(status='NOT_RUN',evidence=[]);self.assertFalse(validate(self.contract,self.root)['ready'])
 def test_no_evidence(self):
  self.contract['acceptance'][0]['evidence']=[]
  with self.assertRaises(ValueError):validate(self.contract,self.root)
 def test_screenshot_is_not_behavior(self):
  self.contract['acceptance'][0]['evidence'][0]['kind']='screenshot'
  with self.assertRaises(ValueError):validate(self.contract,self.root)
 def test_mutations(self):
  for field,value in [('sha256','0'*64),('path','../outside'),('status','FAIL'),('exit_code',7)]:
   with self.subTest(field=field):
    c=copy.deepcopy(self.contract);c['acceptance'][0]['evidence'][0][field]=value
    with self.assertRaises(ValueError):validate(c,self.root)
 def test_symlink(self):
  (self.root/'alias').symlink_to(self.root/'proof.log');self.contract['acceptance'][0]['evidence'][0]['path']='alias'
  with self.assertRaises(ValueError):validate(self.contract,self.root)
 def test_scope_and_owner(self):
  for field,value in [('scope',''),('owned_paths',['/private']),('to_role','executor')]:
   c=copy.deepcopy(self.contract);c[field]=value
   with self.assertRaises(ValueError):validate(c,self.root)
 def test_duplicate_acceptance(self):
  self.contract['acceptance']*=2
  with self.assertRaises(ValueError):validate(self.contract,self.root)
if __name__=='__main__':unittest.main()
