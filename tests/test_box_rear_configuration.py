"""Rear-box patterns retain independent identities, parameters, and assembly poses."""
from dataclasses import replace
from itertools import product
from pathlib import Path
import unittest
from unittest.mock import patch

from vault import __main__ as cli
from vault.assembly import assembly_definition, build_finished_components
from vault.assembly_validation import definition_errors, validation_signature
from vault.box import BoxSpec
from vault.generator import ASSEMBLY_PARTS, Configuration, catalog
from tools.check_assembly import definition_report


class BoxRearConfigurationTests(unittest.TestCase):
    def test_plain_default_and_invalid_values_agree_between_native_and_api(self):
        self.assertEqual(Configuration.parse({}).box_rear_pattern, 'plain')
        self.assertEqual(catalog()['defaults']['box_rear_pattern'], 'plain')
        self.assertEqual([item['id'] for item in catalog()['box_rear_patterns']],
                         ['plain', 'waffle', 'miura'])
        for value in ('unknown', 'Waffle', '', None, True, 1, [], {}):
            for constructor in (BoxSpec, Configuration):
                with self.subTest(value=value, constructor=constructor.__name__), self.assertRaises(ValueError):
                    constructor(box_rear_pattern=value)

    def test_floor_base_and_rear_choices_have_distinct_stable_box_identities(self):
        self.assertEqual(BoxSpec().slug, 's4_box_1f')
        self.assertEqual(BoxSpec(box_floor=3, box_variant='gridfinity').slug,
                         's4_box_1f_floor_3mm_gridfinity')
        variants = [BoxSpec(box_floor=floor, box_variant=base, box_rear_pattern=rear)
                    for floor, base, rear in product((.8, 3.), ('plain', 'gridfinity'), ('plain', 'waffle', 'miura'))]
        variants.extend(BoxSpec(box_floor=0, box_variant='gridfinity', box_rear_pattern=rear)
                        for rear in ('plain', 'waffle', 'miura'))
        self.assertEqual(len({spec.slug for spec in variants}), len(variants))
        self.assertEqual(BoxSpec(box_floor=3, box_variant='gridfinity', box_rear_pattern='miura').slug,
                         's4_box_1f_floor_3mm_gridfinity_rear_miura_corrugated')

    def test_select_spec_preserves_drawer_layout_and_ignores_unrelated_module_patterns(self):
        selected = cli.select_spec('box', 'L', 6, 2, drawer_columns=2, drawer_rows=2,
                                   box_floor=3, box_variant='gridfinity', box_rear_pattern='waffle',
                                   wall_pattern='miura', pattern_pitch=20, pattern_depth=1.4,
                                   pattern_line_width=.8, pattern_construction='corrugated')
        self.assertEqual(selected, BoxSpec('S', 6, 1, 3, 'gridfinity', 'waffle'))
        for kind in (*ASSEMBLY_PARTS, 'key'):
            if kind != 'box':
                self.assertEqual(cli.select_spec(kind), cli.select_spec(kind, box_rear_pattern='waffle'))
        self.assertEqual(cli.select_spec('box', box_rear_pattern='miura'),
                         cli.select_spec('box', box_rear_pattern='miura', wall_pattern='waffle', pattern_pitch=18))

    def test_cli_and_publication_record_rear_choice(self):
        with patch.object(cli, 'build') as build, patch('sys.argv', [
                'vault', 'build', '--part', 'box', '--family', 'M', '--depth-units', '5',
                '--height-units', '2', '--box-variant', 'gridfinity', '--box-floor', '3',
                '--box-rear-pattern', 'miura']):
            cli.main()
        selected = BoxSpec('M', 5, 2, 3, 'gridfinity', 'miura')
        build.assert_called_once_with(cli.PROJECT_ROOT/'out', selected)
        with patch.object(cli, 'run_build') as transaction:
            cli.build(Path('/tmp/box-rear-publication-test'), selected)
        parameters = transaction.call_args.kwargs['parameters']
        self.assertEqual(parameters['box_rear_pattern'], 'miura')
        self.assertEqual(parameters['part'], selected.slug)
        self.assertEqual(transaction.call_args.kwargs['aliases'], [f'latest/{selected.slug}'])

    def test_assembly_keeps_placements_quantities_and_finished_rear_choice(self):
        plain = Configuration('L', 6, 2, drawer_columns=2, drawer_rows=2,
                              box_floor=3, box_variant='gridfinity', wall_pattern='miura')
        patterned = replace(plain, box_rear_pattern='waffle')
        base_scene, scene = assembly_definition(plain), assembly_definition(patterned)
        self.assertEqual(definition_errors(patterned, scene), [])
        self.assertEqual([item['transform'] for item in base_scene['instances']],
                         [item['transform'] for item in scene['instances']])
        self.assertEqual(plain.print_copies, patterned.print_copies)
        self.assertNotEqual(validation_signature(plain), validation_signature(patterned))
        self.assertNotEqual(validation_signature(patterned), validation_signature(replace(patterned, box_rear_pattern='miura')))
        with patch('vault.model.build_module'), patch('vault.box.build_box') as box, \
                patch('vault.facade.build_facade'), patch('vault.geared_rails.build_gear_rail'), \
                patch('vault.runner_guides.build_runner_guide'), patch('vault.runner_slides.build_runner_slide'):
            build_finished_components(patterned)
        self.assertEqual(box.call_args.kwargs, {'spec': BoxSpec('S', 6, 1, 3, 'gridfinity', 'waffle'),
                                               'include_supports': False})

    def test_all_assembly_definitions_accept_each_independent_rear_pattern(self):
        for pattern in ('waffle', 'miura'):
            with self.subTest(pattern=pattern):
                report = definition_report({'box_rear_pattern': pattern, 'box_variant': 'gridfinity'})
                self.assertTrue(report['passed'])
                self.assertTrue(all(case['configuration']['box_rear_pattern'] == pattern
                                    for case in report['cases']))


if __name__ == '__main__':
    unittest.main()
