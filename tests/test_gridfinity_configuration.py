"""Gridfinity requests retain box identity through selection and assembly caches."""
from dataclasses import replace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vault import __main__ as cli
from vault.assembly import assembly_definition, build_finished_components
from vault.assembly_validation import definition_errors, validation_signature
from vault.box import BoxSpec
from vault.generator import ASSEMBLY_PARTS, Configuration, catalog
from vault.web import BuildFiles
from tools import check_assembly


class GridfinityConfigurationTests(unittest.TestCase):
    def test_requests_and_catalog_keep_plain_defaults_and_bound_variants(self):
        self.assertEqual(Configuration.parse({}).box_variant, 'plain')
        self.assertEqual(Configuration.parse({'box_variant': 'gridfinity'}).box_variant, 'gridfinity')
        self.assertEqual(catalog()['defaults']['box_variant'], 'plain')
        self.assertEqual([item['id'] for item in catalog()['box_variants']], ['plain', 'gridfinity'])
        for value in ('GRIDFINITY', 'unknown', '', None, True, 1, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Configuration.parse({'box_variant': value})

    def test_floorless_requires_gridfinity_and_keeps_closed_floor_defaults(self):
        self.assertEqual(catalog()['thicknesses']['box_floor'], [0., .8, 3.])
        self.assertEqual(catalog()['defaults']['box_floor'], .8)
        for constructor in (Configuration, BoxSpec):
            with self.subTest(constructor=constructor.__name__):
                self.assertEqual(constructor(box_floor=0, box_variant='gridfinity').box_floor, 0)
                self.assertEqual(constructor(box_floor=0., box_variant='gridfinity').box_floor, 0)
                self.assertEqual(constructor().box_floor, .8)
                with self.assertRaises(ValueError):
                    constructor(box_floor=0)
                for value in (False, True, -.1, .4, '0', None, float('nan')):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        constructor(box_floor=value, box_variant='gridfinity')

    def test_floorless_identity_and_multi_drawer_mapping_preserve_rear_choice(self):
        closed = BoxSpec(box_variant='gridfinity')
        floorless = replace(closed, box_floor=0)
        self.assertEqual(floorless.slug, 's4_box_1f_floorless_gridfinity')
        self.assertIn('Floorless', floorless.name)
        self.assertEqual(floorless, replace(closed, box_floor=0.))
        self.assertEqual(len({closed.slug, floorless.slug, replace(closed, box_floor=3).slug}), 3)
        for rear in ('plain', 'waffle', 'miura'):
            selected = cli.select_spec('box', 'L', 6, 2, drawer_columns=2, drawer_rows=2,
                                       box_floor=0, box_variant='gridfinity', box_rear_pattern=rear)
            self.assertEqual(selected, BoxSpec('S', 6, 1, 0, 'gridfinity', rear))

    def test_floorless_cli_validates_before_build_and_assembly_checker_forwards_floor(self):
        argv = ['vault', 'build', '--part', 'box', '--box-floor', '0']
        with patch.object(cli, 'build') as build, patch('sys.argv', argv), \
                redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            cli.main()
        build.assert_not_called()
        with patch.object(cli, 'build') as build, patch('sys.argv', [*argv, '--box-variant', 'gridfinity']):
            cli.main()
        build.assert_called_once_with(cli.PROJECT_ROOT/'out', BoxSpec(box_floor=0, box_variant='gridfinity'))
        with tempfile.TemporaryDirectory() as directory, patch('sys.argv', [
                'check_assembly', '--case', 'S4:1', '--box-variant', 'gridfinity', '--box-floor', '0',
                '--box-rear-pattern', 'waffle', '--output', str(Path(directory)/'audit.json')]), \
                patch.object(check_assembly, 'validate_assembly', return_value={'passed': True}) as validate, \
                redirect_stdout(StringIO()):
            check_assembly.main()
        self.assertEqual(validate.call_args.args[0], Configuration(box_floor=0, box_variant='gridfinity',
                                                                 box_rear_pattern='waffle'))

    def test_floorless_assembly_keeps_transforms_and_requires_its_own_receipt(self):
        closed = Configuration('L', 6, 2, box_variant='gridfinity', drawer_columns=2, drawer_rows=2,
                               box_rear_pattern='miura')
        floorless = replace(closed, box_floor=0)
        self.assertEqual([item['transform'] for item in assembly_definition(closed)['instances']],
                         [item['transform'] for item in assembly_definition(floorless)['instances']])
        self.assertEqual(closed.print_copies, floorless.print_copies)
        self.assertNotEqual(validation_signature(closed), validation_signature(floorless))
        self.assertEqual(validation_signature(floorless), validation_signature(replace(floorless, box_floor=0.)))
        with patch('vault.model.build_module'), patch('vault.box.build_box') as box, \
                patch('vault.facade.build_facade'), patch('vault.geared_rails.build_gear_rail'), \
                patch('vault.runner_guides.build_runner_guide'), patch('vault.runner_slides.build_runner_slide'):
            build_finished_components(floorless)
        self.assertEqual(box.call_args.kwargs, {'spec': BoxSpec('S', 6, 1, 0, 'gridfinity', 'miura'),
                                               'include_supports': False})

    def test_selection_keeps_matching_drawer_sizes_and_other_part_identities(self):
        plain = cli.select_spec('box')
        self.assertEqual(plain.slug, 's4_box_1f')
        gridfinity = cli.select_spec('box', box_variant='gridfinity')
        self.assertEqual(gridfinity.slug, 's4_box_1f_gridfinity')
        self.assertEqual(cli.part_kind(gridfinity), 'box')
        self.assertEqual(gridfinity.box_variant, 'gridfinity')
        four = cli.select_spec('box', 'L', 6, 2, drawer_columns=2, drawer_rows=2,
                               box_floor=3., box_variant='gridfinity')
        self.assertEqual((four.family, four.depth_units, four.height_units, four.box_floor),
                         ('S', 6, 1, 3.))
        self.assertNotEqual(four.slug, cli.select_spec('box', 'S', 6, 1,
                                                      box_variant='gridfinity').slug)
        for kind in ASSEMBLY_PARTS:
            if kind != 'box':
                self.assertEqual(cli.select_spec(kind), cli.select_spec(kind, box_variant='gridfinity'))

    def test_cli_passes_variant_to_the_checked_build_pipeline(self):
        with patch.object(cli, 'build') as build, patch('sys.argv', [
                'vault', 'build', '--part', 'box', '--family', 'M', '--depth-units', '5',
                '--height-units', '2', '--box-variant', 'gridfinity', '--box-floor', '3']):
            cli.main()
        build.assert_called_once_with(cli.PROJECT_ROOT / 'out',
                                      cli.select_spec('box', 'M', 5, 2, box_variant='gridfinity', box_floor=3.))

    def test_assembly_preserves_placements_and_separates_fit_receipts(self):
        for config in (Configuration(), Configuration('M', 3, 2),
                       Configuration('L', 6, 2, drawer_columns=2, drawer_rows=2)):
            gridfinity = replace(config, box_variant='gridfinity')
            plain_scene, grid_scene = assembly_definition(config), assembly_definition(gridfinity)
            self.assertEqual(definition_errors(gridfinity, grid_scene), [])
            self.assertEqual([item['transform'] for item in plain_scene['instances']],
                             [item['transform'] for item in grid_scene['instances']])
            self.assertEqual(config.print_copies, gridfinity.print_copies)
            self.assertNotEqual(validation_signature(config), validation_signature(gridfinity))


class GridfinityCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.files = BuildFiles(self.root)
        self.serial = 0

    def save(self, kind, *, variant=None, floor=.8):
        self.serial += 1
        build_id = f'20261027T010000{self.serial:06d}Z-0123456789ab'
        directory = self.root / 'builds' / build_id
        directory.mkdir(parents=True)
        slug = {'module': 's4_module_1f', 'box': 's4_box_1f', 'facade': 's1f_facade',
                'rails': 's_geared_rails', 'runner_guides': 'x4_runner_guides',
                'runner_slides': 'x4_runner_slides'}[kind]
        parameters = dict(family='S', depth_units=4, height_units=1, part=slug)
        if kind == 'box':
            parameters['box_floor'] = floor
            if variant is not None:
                parameters['box_variant'] = variant
        (directory / 'resolved-parameters.json').write_text(json.dumps(parameters))
        roles = {'rails': ('plain', 'retained'), 'runner_guides': ('left', 'right'),
                 'runner_slides': ('left', 'right')}.get(kind, ('single',))
        parts, checksums = {}, {}
        for role in roles:
            path = f'preview/assembly/{role}.stl'
            checksums[path] = 'fixture-checksum'
            parts[role] = {'assembly_mesh': {'schema': 'vault-assembly-mesh/v1', 'finished': True,
                                           'coordinates': 'native', 'component': role, 'path': path}}
        (directory / 'manifest.json').write_text(json.dumps({
            'passed': True, 'build_id': build_id, 'parts': parts, 'checksums': checksums,
            'git': {'commit': 'current', 'dirty': False}, 'source_hash': 'same-source'}))
        return build_id

    @patch('vault.web.git_provenance', return_value={'commit': 'current', 'dirty': False})
    def test_old_boxes_stay_plain_and_gridfinity_caches_never_replace_them(self, _):
        common = [self.save(kind) for kind in ASSEMBLY_PARTS if kind != 'box']
        plain = self.save('box')
        self.assertEqual(self.files.describe(plain)['configuration']['box_variant'], 'plain')
        grid_config = Configuration(box_variant='gridfinity')
        scene = self.files.assembly(grid_config)
        self.assertFalse(scene['complete'])
        self.assertEqual({item['kind'] for item in scene['missing']}, {'box'})
        grid = self.save('box', variant='gridfinity')
        self.save('box', variant='gridfinity', floor=3.)
        for config, expected in ((Configuration(), plain), (grid_config, grid)):
            scene = self.files.assembly(config)
            self.assertTrue(scene['complete'])
            self.assertEqual({item['build_id'] for item in scene['instances']}, {*common, expected})
        receipt = self.root / 'web' / 'assemblies' / 'gridfinity.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({'configuration': grid_config.as_dict(),
                                      'validation_signature': validation_signature(grid_config),
                                      'build_ids': [*common, grid], 'validation': {'passed': True}}))
        self.assertTrue(self.files.assembly(grid_config)['validation']['passed'])
        self.assertIsNone(self.files.assembly(Configuration())['validation'])

    @patch('vault.web.git_provenance', return_value={'commit': 'current', 'dirty': False})
    def test_floorless_and_closed_gridfinity_caches_do_not_replace_each_other(self, _):
        common = [self.save(kind) for kind in ASSEMBLY_PARTS if kind != 'box']
        thin = self.save('box', variant='gridfinity')
        thick = self.save('box', variant='gridfinity', floor=3)
        floorless_config = Configuration(box_variant='gridfinity', box_floor=0)
        missing = self.files.assembly(floorless_config)
        self.assertFalse(missing['complete'])
        self.assertEqual({item['kind'] for item in missing['missing']}, {'box'})
        floorless = self.save('box', variant='gridfinity', floor=0)
        self.assertEqual(self.files.describe(floorless)['configuration']['box_floor'], 0)
        for floor, expected in ((0, floorless), (.8, thin), (3, thick)):
            scene = self.files.assembly(replace(floorless_config, box_floor=floor))
            self.assertTrue(scene['complete'])
            self.assertEqual({item['build_id'] for item in scene['instances']}, {*common, expected})
        receipt = self.root/'web/assemblies/floorless.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({'configuration': floorless_config.as_dict(),
                                      'validation_signature': validation_signature(floorless_config),
                                      'build_ids': [*common, floorless], 'validation': {'passed': True}}))
        scene = self.files.assembly(floorless_config)
        self.assertTrue(scene['validation']['passed'])
        self.assertIn('Floorless Gridfinity', scene['name'])
        self.assertIsNone(self.files.assembly(replace(floorless_config, box_floor=.8))['validation'])


if __name__ == '__main__':
    unittest.main()
