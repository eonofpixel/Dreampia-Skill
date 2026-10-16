import json,pathlib,shutil,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import skill_bundle,team_cli as team

class SkillBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=pathlib.Path(self.tmp.name);self.source=self.base/'source';shutil.copytree(team.PACKAGE,self.source,ignore=shutil.ignore_patterns('evidence','__pycache__'));self.skill=self.source/'ai-dev-execution';self.project=self.base/'project';self.project.mkdir()
    def tearDown(self):self.tmp.cleanup()
    def reject(self):
        with self.assertRaises(team.InstallError):team.install(self.project,'init',True,self.source)
        self.assertEqual(list(self.project.iterdir()),[])
    def edit_manifest(self,edit):
        p=self.skill/skill_bundle.NAME;m=json.loads(p.read_text());edit(m);p.write_text(json.dumps(m))
    def test_missing_required_reference_blocks_before_project_write(self):
        (self.skill/'references/local-verification.md').unlink();self.reject()
    def test_tampered_and_unlisted_files_block_before_project_write(self):
        p=self.skill/'references/local-verification.md';old=p.read_bytes();p.write_text('changed');self.reject();p.write_bytes(old)
        (self.skill/'references/unregistered.md').write_text('unexpected');self.reject()
    def test_missing_manifest_and_version_mismatch_block(self):
        p=self.skill/skill_bundle.NAME;old=p.read_bytes();p.unlink();self.reject();p.write_bytes(old)
        self.edit_manifest(lambda m:m.update(version='99.0.0'));self.reject()
    def test_schema_paths_duplicate_and_frontmatter_fail_closed(self):
        original=(self.skill/skill_bundle.NAME).read_bytes()
        edits=[lambda m:m.update(filez=[]),lambda m:m['files'].append(dict(m['files'][0])),lambda m:m['files'][0].update(path='../outside'),lambda m:m['files'][0].update(required='yes'),lambda m:m['files'][0].update(sha256='bad')]
        for edit in edits:
            with self.subTest(edit=edit):
                (self.skill/skill_bundle.NAME).write_bytes(original);self.edit_manifest(edit);self.reject()
        (self.skill/skill_bundle.NAME).write_bytes(original);(self.skill/'SKILL.md').write_text('not frontmatter')
        with self.assertRaises(ValueError):skill_bundle.write(self.skill,team.VERSION)
    def test_optional_absence_is_explicit_and_present_hash_still_required(self):
        n='assets/examples/README.md';data=(self.skill/n).read_bytes();self.edit_manifest(lambda m:next(x for x in m['files'] if x['path']==n).update(required=False));(self.skill/n).unlink()
        result=skill_bundle.validate(skill_bundle.read(self.skill),team.VERSION);self.assertEqual(result['missing_optional'],[n]);team.install(self.project,'init',True,self.source);self.assertTrue(team.doctor(self.project)['healthy'])
        (self.skill/n).write_bytes(data+b'bad')
        with self.assertRaises(ValueError):skill_bundle.validate(skill_bundle.read(self.skill),team.VERSION)
    def test_generated_inventory_is_deterministic_and_installed_bytes_match(self):
        p=self.skill/skill_bundle.NAME;before=p.read_bytes();info=skill_bundle.write(self.skill,team.VERSION);self.assertEqual(p.read_bytes(),before);self.assertEqual(info['missing_optional'],[])
        team.install(self.project,'init',True,self.source);target=self.project/team.SKILL/skill_bundle.NAME;self.assertEqual(target.read_bytes(),before)
        doctor=team.doctor(self.project);self.assertTrue(doctor['healthy']);self.assertEqual(doctor['skill_bundle']['manifest_sha256'],info['manifest_sha256']);self.assertEqual(doctor['skill_bundle']['status'],'VALID')
    def test_doctor_detects_unlisted_file_and_symlink_added_after_install(self):
        team.install(self.project,'init',True,self.source);root=self.project/team.SKILL
        p=root/'references/extra.md';p.write_text('unexpected');self.assertFalse(team.doctor(self.project)['healthy']);p.unlink()
        p.symlink_to(self.skill/'SKILL.md');self.assertFalse(team.doctor(self.project)['healthy'])
    def test_source_and_bundle_cannot_override_runtime_version(self):
        (self.source/'VERSION').write_text('99.0.0');self.edit_manifest(lambda m:m.update(version='99.0.0'));self.reject()
