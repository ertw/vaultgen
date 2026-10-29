"""Assembly API resolves immutable native meshes and reports missing/legacy caches."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vault.generator import Configuration, ASSEMBLY_PARTS, ACCESSORY_PARTS
from vault.assembly_validation import validation_signature
from vault.web_builds import BuildFiles


class AssemblyCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.files = BuildFiles(self.root)
        self.serial = 0

    def tearDown(self):
        self.temp.cleanup()

    def build(self, kind, *, legacy=False, floor=.8, family='S', columns=None, rows=None, height=1,
              pattern=None, pitch=14., depth=1.7, line_width=.65, faces='all', construction=None,
              box_rear=None, box_variant='plain', facade_floor=None):
        self.serial += 1
        build_id = f'20261024T010000{self.serial:06d}Z-0123456789ab'
        directory = self.root / 'builds' / build_id
        directory.mkdir(parents=True)
        part = {'module':'s4_module_1f','box':'s4_box_1f','facade':'s1f_facade',
                'rails':'s_geared_rails','runner_guides':'x4_runner_guides',
                'runner_slides':'x4_runner_slides', 'key':'snap_key'}.get(kind, kind)
        if kind == 'module':
            layout = ('_2_columns' if columns == 2 else '') + ('_2_rows' if rows == 2 else '')
            part = f'{family.lower()}4{layout}_module_{height}f'
        if kind == 'facade' and facade_floor == .8:
            part += '_floor_0p8'
        roles = {'rails':['plain','retained'],'runner_guides':['left','right'],
                 'runner_slides':['left','right'], 'key':['key']}.get(kind,['single'])
        parameters = dict(family=family,depth_units=4,height_units=height,part=part)
        if columns is not None: parameters['drawer_columns'] = columns
        if rows is not None: parameters['drawer_rows'] = rows
        if kind == 'facade' and facade_floor is not None:
            parameters['facade_floor'] = facade_floor
        if kind == 'box':
            parameters['box_floor'] = floor
            parameters['box_variant'] = box_variant
            if box_rear is not None:
                parameters['box_rear_pattern'] = box_rear
        if kind == 'module' and pattern is not None:
            parameters.update(wall_pattern=pattern, pattern_pitch=pitch, pattern_depth=depth,
                              pattern_line_width=line_width, pattern_faces=faces)
            if construction is not None:
                parameters['pattern_construction'] = construction
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

    def write_receipt(self, path, record):
        kinds = {build_id: self.files.describe(build_id)['kind'] for build_id in record['build_ids']}
        record['build_ids'] = [build_id for build_id, kind in kinds.items() if kind in ASSEMBLY_PARTS]
        record['accessory_build_ids'] = [build_id for build_id, kind in kinds.items() if kind in ACCESSORY_PARTS]
        path.write_text(json.dumps(record))

    @patch('vault.web_builds.git_provenance', return_value={'commit': 'current', 'dirty': False})
    def test_registered_facade_materials_keep_one_instance_and_checked_urls(self, _):
        build_id = self.build('facade')
        directory = self.root / 'builds' / build_id
        manifest_path = directory / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        materials = {}
        for name, role in [('body', 'primary'), ('locked', 'secondary'), ('unlocked', 'secondary')]:
            native = f'preview/assembly/{name}.stl'
            printable = f'preview/materials/{name}.stl'
            for relative in (native, printable):
                path = directory / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'checked material')
                manifest['checksums'][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            materials[name] = {'role': role, 'print_path': printable, 'assembly_mesh': {
                'schema': 'vault-assembly-mesh/v1', 'coordinates': 'native', 'finished': True, 'path': native}}
        manifest['parts']['single']['materials'] = materials
        manifest_path.write_text(json.dumps(manifest))
        scene = self.files.assembly(Configuration())
        self.assertEqual(len(scene['instances']), 1)
        facade = scene['instances'][0]
        self.assertEqual(facade['id'], 'facade')
        self.assertEqual([m['role'] for m in facade['material_meshes']], ['primary', 'secondary', 'secondary'])
        for material in facade['material_meshes']:
            self.assertEqual(self.files.artifact(build_id, material['mesh_url'].split(f'/{build_id}/')[1]),
                             b'checked material')
        del manifest['checksums']['preview/materials/locked.stl']
        manifest_path.write_text(json.dumps(manifest))
        self.assertEqual(self.files.describe(build_id)['parts'][0]['material_meshes'], [])

    @patch('vault.web_builds.git_provenance', return_value={'commit': 'current', 'dirty': False})
    def test_facade_floor_cache_keeps_legacy_default_and_exact_fit_receipt(self, _):
        common = [self.build(kind) for kind in (*ASSEMBLY_PARTS, *ACCESSORY_PARTS) if kind != 'facade']
        legacy = self.build('facade')
        self.assertEqual(self.files.describe(legacy)['configuration']['facade_floor'], 'default')
        selected = Configuration(facade_floor=.8)
        missing = self.files.assembly(selected)
        self.assertFalse(missing['complete'])
        self.assertEqual({item['kind'] for item in missing['missing']}, {'facade'})
        shelled = self.build('facade', facade_floor=.8)
        for config, expected in ((Configuration(), legacy), (selected, shelled)):
            scene = self.files.assembly(config)
            self.assertTrue(scene['complete'])
            self.assertEqual({item['build_id'] for item in scene['instances']}, {*common, expected})
        receipt = self.root / 'web/assemblies/facade-floor.json'
        receipt.parent.mkdir(parents=True)
        self.write_receipt(receipt, dict(configuration=selected.as_dict(),
            validation_signature=validation_signature(selected), build_ids=[*common, shelled],
            validation={'passed': True}))
        self.assertTrue(self.files.assembly(selected)['validation']['passed'])
        self.assertIsNone(self.files.assembly(Configuration())['validation'])

    @patch('vault.web_builds.git_provenance', return_value={'commit': 'current', 'dirty': False})
    def test_box_rear_cache_and_receipts_preserve_independent_module_and_base_choices(self, _):
        from dataclasses import replace
        common = [self.build(kind) for kind in (*ASSEMBLY_PARTS, *ACCESSORY_PARTS) if kind not in ('box', 'module')]
        module = self.build('module', pattern='miura', pitch=20, depth=1.4,
                            line_width=.8, construction='corrugated')
        config = Configuration(wall_pattern='miura', pattern_pitch=20, pattern_depth=1.4,
                               pattern_line_width=.8, pattern_construction='corrugated')
        legacy = self.build('box')
        self.assertEqual(self.files.describe(legacy)['configuration']['box_rear_pattern'], 'plain')
        for rear in ('waffle', 'miura'):
            missing = self.files.assembly(replace(config, box_rear_pattern=rear))
            self.assertFalse(missing['complete'])
            self.assertEqual({item['kind'] for item in missing['missing']}, {'box'})
        waffle = self.build('box', box_rear='waffle')
        miura = self.build('box', box_rear='miura')
        grid = self.build('box', box_rear='waffle', box_variant='gridfinity')
        self.build('box', box_rear='waffle', box_variant='gridfinity', floor=3.)
        for rear, variant, expected in (('plain', 'plain', legacy), ('waffle', 'plain', waffle),
                                        ('miura', 'plain', miura), ('waffle', 'gridfinity', grid)):
            scene = self.files.assembly(replace(config, box_rear_pattern=rear, box_variant=variant))
            self.assertTrue(scene['complete'])
            self.assertEqual({item['build_id'] for item in scene['instances']}, {*common, module, expected})
        selected = replace(config, box_rear_pattern='waffle', box_variant='gridfinity')
        receipt = self.root / 'web/assemblies/box-rear.json'
        receipt.parent.mkdir(parents=True)
        self.write_receipt(receipt, dict(configuration=selected.as_dict(),
            validation_signature=validation_signature(selected), build_ids=[*common, module, grid],
            validation={'passed': True}))
        scene = self.files.assembly(selected)
        self.assertTrue(scene['validation']['passed'])
        self.assertIn('Waffle corrugated box rear', scene['name'])
        self.assertIsNone(self.files.assembly(replace(selected, box_variant='plain'))['validation'])
        mismatch = self.files.assembly(replace(selected, box_rear_pattern='miura'))
        self.assertFalse(mismatch['complete'])
        self.assertEqual({item['kind'] for item in mismatch['missing']}, {'box'})

    @patch('vault.web_builds.git_provenance',return_value={'commit':'current','dirty':False})
    def test_pattern_module_cache_and_fit_receipts_match_every_geometry_parameter(self, _):
        from dataclasses import replace
        other_parts = [self.build(kind) for kind in (*ASSEMBLY_PARTS, *ACCESSORY_PARTS) if kind != 'module']
        plain = self.build('module')
        waffle = self.build('module', pattern='waffle')
        custom = self.build('module', pattern='miura', pitch=20, depth=1.4, line_width=.8, faces='sides',
                            construction='corrugated')
        config = Configuration(wall_pattern='miura', pattern_pitch=20, pattern_depth=1.4,
                               pattern_line_width=.8, pattern_faces='sides', pattern_construction='corrugated')
        for selected, expected in ((Configuration(), plain), (Configuration(wall_pattern='waffle'), waffle),
                                   (config, custom)):
            scene = self.files.assembly(selected)
            self.assertTrue(scene['complete'])
            self.assertEqual({i['build_id'] for i in scene['instances']}, {*other_parts, expected})
        for values in ({'pattern_pitch': 21}, {'pattern_depth': 1.3},
                       {'pattern_line_width': .7}, {'pattern_faces': 'all'}, {'wall_pattern': 'waffle'},
                       {'pattern_construction': 'recessed'}):
            scene = self.files.assembly(replace(config, **values))
            self.assertFalse(scene['complete'])
            self.assertEqual({item['kind'] for item in scene['missing']}, {'module'})
        receipt = self.root / 'web/assemblies/pattern.json'
        receipt.parent.mkdir(parents=True)
        self.write_receipt(receipt, dict(configuration=config.as_dict(),
            validation_signature=validation_signature(config), build_ids=[*other_parts, custom],
            validation={'passed': True}))
        self.assertTrue(self.files.assembly(config)['validation']['passed'])
        self.assertIsNone(self.files.assembly(Configuration(wall_pattern='waffle'))['validation'])

    @patch('vault.web_builds.git_provenance',return_value={'commit':'current','dirty':False})
    def test_complete_scene_pins_all_builds_and_requires_check_receipt(self, _):
        ids = [self.build(kind) for kind in (*ASSEMBLY_PARTS, *ACCESSORY_PARTS)]
        scene = self.files.assembly(Configuration())
        self.assertTrue(scene['complete'])
        self.assertEqual(len(scene['instances']),18)
        self.assertEqual({i['build_id'] for i in scene['instances']},set(ids))
        self.assertTrue(any('fit check' in w for w in scene['warnings']))
        receipt = self.root / 'web/assemblies/job.json'
        receipt.parent.mkdir(parents=True)
        self.write_receipt(receipt, dict(configuration=Configuration().as_dict(),
            validation_signature=validation_signature(Configuration()),
            build_ids=ids,validation={'passed':True}))
        scene = self.files.assembly(Configuration())
        self.assertEqual(scene['warnings'],[])
        self.assertTrue(scene['validation']['passed'])
        with patch('vault.assembly_validation.validation_signature', return_value='changed-definition'):
            changed = self.files.assembly(Configuration())
        self.assertIsNone(changed['validation'])
        self.assertTrue(any('fit check' in warning for warning in changed['warnings']))

    @patch('vault.web_builds.git_provenance', return_value={'commit': 'current', 'dirty': False})
    def test_accessory_availability_and_exact_receipts_are_required(self, _):
        ids = [self.build(kind) for kind in ASSEMBLY_PARTS]
        scene = self.files.assembly(Configuration())
        self.assertFalse(scene['complete'])
        self.assertEqual({item['kind'] for item in scene['missing']}, set(ACCESSORY_PARTS))
        ids += [self.build(kind) for kind in ACCESSORY_PARTS]
        scene = self.files.assembly(Configuration())
        self.assertTrue(scene['complete'])
        self.assertEqual(scene['validation_scope'], 'drawer_components')
        self.assertEqual({item['kind'] for item in scene['instances']}, set(Configuration().parts))
        self.assertEqual(len({item['mesh_url'] for item in scene['instances']}), 15)
        receipt = self.root / 'web/assemblies/complete.json'
        receipt.parent.mkdir(parents=True)
        self.write_receipt(receipt, dict(configuration=Configuration().as_dict(),
            validation_signature=validation_signature(Configuration()), build_ids=ids,
            validation={'passed': True, 'scope': 'drawer_components'}))
        self.assertTrue(self.files.assembly(Configuration())['validation']['passed'])
        # Even a compatible newer accessory must not inherit another build's receipt.
        self.build('spring')
        changed = self.files.assembly(Configuration())
        self.assertTrue(changed['complete'])
        self.assertIsNone(changed['validation'])
        self.build('key_cap', legacy=True)
        legacy = self.files.assembly(Configuration())
        self.assertFalse(legacy['complete'])
        self.assertEqual({item['kind'] for item in legacy['missing']}, {'key_cap'})

    @patch('vault.web_builds.git_provenance',return_value={'commit':'current','dirty':True})
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

    @patch('vault.web_builds.git_provenance',return_value={'commit':'current','dirty':False})
    def test_two_drawer_scene_reuses_s_parts_and_distinguishes_l_modules(self, _):
        drawer_builds = {kind: self.build(kind) for kind in (*ASSEMBLY_PARTS, *ACCESSORY_PARTS) if kind != 'module'}
        single_module = self.build('module', family='L')
        double_module = self.build('module', family='L', columns=2)
        # Newer wide L drawer components must not replace the matching S parts.
        for kind in ('box', 'facade', 'rails'):
            self.build(kind, family='L')
        configuration = Configuration(family='L', drawer_columns=2)
        scene = self.files.assembly(configuration)
        self.assertTrue(scene['complete'])
        self.assertEqual(len(scene['instances']), 35)
        self.assertEqual(next(item['build_id'] for item in scene['instances'] if item['kind'] == 'module'), double_module)
        for kind, build_id in drawer_builds.items():
            instances = [item for item in scene['instances'] if item['kind'] == kind]
            self.assertEqual({item['build_id'] for item in instances}, {build_id})
            self.assertGreaterEqual(len(instances), 2)
        single = self.files.assembly(Configuration(family='L'))
        self.assertEqual(next(item['build_id'] for item in single['instances'] if item['kind'] == 'module'), single_module)
        self.assertEqual(self.files.describe(double_module)['configuration']['drawer_columns'], 2)
        self.assertEqual(self.files.describe(single_module)['configuration']['drawer_columns'], 1)

    @patch('vault.web_builds.git_provenance',return_value={'commit':'current','dirty':False})
    def test_two_and_four_drawer_scenes_share_open_module_but_keep_matching_drawers(self, _):
        drawers = {kind: self.build(kind) for kind in (*ASSEMBLY_PARTS, *ACCESSORY_PARTS) if kind != 'module'}
        shared_module = self.build('module', family='L', columns=2, height=2)
        partitioned_module = self.build('module', family='L', columns=2, rows=2, height=2)
        tall_drawers = {kind: self.build(kind, family='S', height=2) for kind in ('box', 'facade')}
        four_configuration = Configuration(family='L', height_units=2, drawer_columns=2, drawer_rows=2)
        scene = self.files.assembly(four_configuration)
        self.assertTrue(scene['complete'])
        self.assertEqual(len(scene['instances']), 67)
        self.assertEqual(next(item['build_id'] for item in scene['instances'] if item['kind'] == 'module'), shared_module)
        for kind, build_id in drawers.items():
            instances = [item for item in scene['instances'] if item['kind'] == kind]
            self.assertEqual({item['build_id'] for item in instances}, {build_id})
            self.assertGreaterEqual(len(instances), 2 if kind == 'latch' else 4)
        double = self.files.assembly(Configuration(family='L', height_units=2, drawer_columns=2))
        self.assertTrue(double['complete'])
        self.assertEqual(len(double['instances']), 51)
        self.assertEqual(next(item['build_id'] for item in double['instances'] if item['kind'] == 'module'), shared_module)
        for kind, build_id in tall_drawers.items():
            self.assertEqual({item['build_id'] for item in double['instances'] if item['kind'] == kind}, {build_id})
        self.assertFalse(self.files.describe(shared_module)['legacy_partitioned_module'])
        self.assertTrue(self.files.describe(partitioned_module)['legacy_partitioned_module'])
        self.assertIn(partitioned_module, {item['id'] for item in self.files.history()})
        receipt = self.root / 'web/assemblies/four.json'
        receipt.parent.mkdir(parents=True)
        self.write_receipt(receipt, dict(configuration=four_configuration.as_dict(),
            validation_signature=validation_signature(four_configuration),
            build_ids=list({item['build_id'] for item in scene['instances']}), validation={'passed': True}))
        self.assertTrue(self.files.assembly(four_configuration)['validation']['passed'])
        self.assertIsNone(self.files.assembly(Configuration(family='L', height_units=2, drawer_columns=2))['validation'])

    @patch('vault.web_builds.git_provenance',return_value={'commit':'current','dirty':False})
    def test_partitioned_history_is_not_used_as_the_shared_open_module(self, _):
        old = self.build('module', family='L', columns=2, rows=2, height=2)
        for rows in (1, 2):
            scene = self.files.assembly(Configuration(family='L', height_units=2,
                                                       drawer_columns=2, drawer_rows=rows))
            self.assertFalse(scene['complete'])
            self.assertFalse(any(item['kind'] == 'module' for item in scene['instances']))
        self.assertTrue(self.files.artifact(old, 'preview/assembly/single.stl'))
