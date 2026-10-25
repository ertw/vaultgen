"""Assembly API resolves immutable native meshes and reports missing/legacy caches."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vault.generator import Configuration
from vault.assembly_validation import validation_signature
from vault.web import BuildFiles


class AssemblyCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.files = BuildFiles(self.root)
        self.serial = 0

    def tearDown(self):
        self.temp.cleanup()

    def build(self, kind, *, legacy=False, floor=.8):
        self.serial += 1
        build_id = f'20261024T010000{self.serial:06d}Z-0123456789ab'
        directory = self.root / 'builds' / build_id
        directory.mkdir(parents=True)
        part = {'module':'s4_module_1f','box':'s4_box_1f','facade':'s1f_facade',
                'rails':'s_geared_rails','runner_guides':'x4_runner_guides',
                'runner_slides':'x4_runner_slides'}[kind]
        roles = {'rails':['plain','retained'],'runner_guides':['left','right'],
                 'runner_slides':['left','right']}.get(kind,['single'])
        parameters = dict(family='S',depth_units=4,height_units=1,part=part)
        if kind == 'box': parameters['box_floor'] = floor
        (directory / 'resolved-parameters.json').write_text(json.dumps(parameters))
        reports, checksums = {}, {}
        for role in roles:
            mesh = f'preview/assembly/{role}.stl'
            path = directory / mesh
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'checked native mesh')
            checksums[mesh] = hashlib.sha256(path.read_bytes()).hexdigest()
            reports[role] = {} if legacy else {'assembly_mesh': {
                'schema':'vault-assembly-mesh/v1','finished':True,'coordinates':'native',
                'component':role,'path':mesh}}
        (directory / 'manifest.json').write_text(json.dumps(dict(
            passed=True,build_id=build_id,parts=reports,checksums=checksums,
            git={'commit':'current','dirty':False},source_hash='same-source')))
        return build_id

    @patch('vault.web.git_provenance',return_value={'commit':'current','dirty':False})
    def test_complete_scene_pins_all_builds_and_requires_check_receipt(self, _):
        ids = [self.build(kind) for kind in Configuration().parts]
        scene = self.files.assembly(Configuration())
        self.assertTrue(scene['complete'])
        self.assertEqual(len(scene['instances']),9)
        self.assertEqual({i['build_id'] for i in scene['instances']},set(ids))
        self.assertTrue(any('fit check' in w for w in scene['warnings']))
        receipt = self.root / 'web/assemblies/job.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps(dict(configuration=Configuration().as_dict(),
            validation_signature=validation_signature(Configuration()),
            build_ids=ids,validation={'passed':True})))
        scene = self.files.assembly(Configuration())
        self.assertEqual(scene['warnings'],[])
        self.assertTrue(scene['validation']['passed'])
        with patch('vault.assembly_validation.validation_signature', return_value='changed-definition'):
            changed = self.files.assembly(Configuration())
        self.assertIsNone(changed['validation'])
        self.assertTrue(any('fit check' in warning for warning in changed['warnings']))

    @patch('vault.web.git_provenance',return_value={'commit':'current','dirty':True})
    def test_old_and_mismatched_meshes_are_missing_not_guessed(self, _):
        self.build('module',legacy=True)
        self.build('box',floor=3)
        self.build('rails')
        scene = self.files.assembly(Configuration())
        self.assertFalse(scene['complete'])
        self.assertEqual({i['kind'] for i in scene['instances']},{'rails'})
        self.assertTrue(any('Rebuild' in i['reason'] for i in scene['missing'] if i['kind']=='module'))
        self.assertTrue(any('Not generated' in i['reason'] for i in scene['missing'] if i['kind']=='box'))
        self.assertTrue(any('uncommitted' in w for w in scene['warnings']))
