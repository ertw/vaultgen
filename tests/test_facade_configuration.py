"""Shelled facades retain exact request, export and assembly identities."""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from vault import __main__ as cli, build as builds
from vault.assembly import assembly_definition, build_finished_components
from vault.assembly_validation import validation_signature
from vault.facade import FacadeSpec
from vault.generator import ASSEMBLY_PARTS, Configuration, catalog


class FacadeConfigurationTests(unittest.TestCase):
    def test_legacy_default_and_bounded_minimum_floor_agree_with_native_spec(self):
        self.assertEqual(Configuration.parse({}).facade_floor, 'default')
        self.assertEqual(catalog()['defaults']['facade_floor'], 'default')
        self.assertEqual(catalog()['thicknesses']['facade_floor'], [.8, 'default'])
        self.assertEqual(catalog()['thickness_applicability'],
                         {'minimum_floor': ['box', 'facade'], 'perimeters': ['module']})
        for value in (.8, 'default'):
            self.assertEqual(Configuration.parse({'facade_floor': value}).facade_floor, value)
        for value in (0, 3, .9, '0.8', '', None, True, [], {}, float('nan')):
            for constructor in (FacadeSpec, Configuration):
                with self.subTest(value=value, constructor=constructor.__name__), self.assertRaises(ValueError):
                    constructor(facade_floor=value)

    def test_selection_identifies_only_facade_variant_and_keeps_drawer_layout(self):
        selected = builds.select_spec('facade', 'L', 6, 2, drawer_columns=2, drawer_rows=2,
                                     facade_floor=.8)
        self.assertEqual(selected, FacadeSpec('S', 1, facade_floor=.8))
        self.assertEqual(selected.slug, 's1f_facade_floor_0p8')
        self.assertEqual(FacadeSpec().slug, 's1f_facade')
        self.assertEqual(builds.part_kind(selected), 'facade')
        for kind in (*ASSEMBLY_PARTS, 'key'):
            if kind != 'facade':
                self.assertEqual(builds.select_spec(kind), builds.select_spec(kind, facade_floor=.8))

    def test_cli_and_publication_keep_distinct_parameters_and_aliases(self):
        for floor in ('0.8', 'default'):
            with patch.object(cli, 'build') as build, patch('sys.argv', [
                    'vault', 'build', '--part', 'facade', '--family', 'M', '--height-units', '2',
                    '--facade-floor', floor]):
                cli.main()
            selected = FacadeSpec('M', 2, facade_floor=.8 if floor == '0.8' else 'default')
            build.assert_called_once_with(cli.PROJECT_ROOT / 'out', selected)
            with patch.object(builds, 'run_build') as transaction:
                builds.build(Path('/tmp/facade-publication-test'), selected)
            parameters = transaction.call_args.kwargs['parameters']
            self.assertEqual(parameters['facade_floor'], selected.facade_floor)
            self.assertEqual(parameters['part'], selected.slug)
            self.assertEqual(transaction.call_args.kwargs['aliases'], [f'latest/{selected.slug}'])

    def test_assembly_uses_chosen_finished_facade_without_changing_placement(self):
        plain = Configuration('L', 6, 2, drawer_columns=2, drawer_rows=2)
        shelled = replace(plain, facade_floor=.8)
        base, scene = assembly_definition(plain), assembly_definition(shelled)
        self.assertEqual([item['transform'] for item in base['instances']],
                         [item['transform'] for item in scene['instances']])
        self.assertEqual(plain.print_copies, shelled.print_copies)
        self.assertNotEqual(validation_signature(plain), validation_signature(shelled))
        with patch('vault.model.build_module'), patch('vault.box.build_box'), \
                patch('vault.facade.build_facade') as facade, patch('vault.geared_rails.build_gear_rail'), \
                patch('vault.runner_guides.build_runner_guide'), patch('vault.runner_slides.build_runner_slide'):
            build_finished_components(shelled)
        self.assertEqual(facade.call_args.kwargs, {'spec': FacadeSpec('S', 1, facade_floor=.8)})

    def test_shelled_print_orientation_puts_front_on_bed_and_rear_upward(self):
        from build123d import Box, Pos
        native = Pos(0, 5, 23.5) * Box(100, 10, 47)
        front_down = builds.print_orientation(native, FacadeSpec(facade_floor=.8))
        self.assertAlmostEqual(front_down.bounding_box().min.Z, 0)
        self.assertAlmostEqual(front_down.bounding_box().max.Z, 10)
        # Native facade Z grows along positive print Y, unlike rear-down export.
        self.assertAlmostEqual(front_down.bounding_box().min.Y, 0)
        self.assertAlmostEqual(front_down.bounding_box().max.Y, 47)
        rear_down = builds.print_orientation(native, FacadeSpec())
        self.assertAlmostEqual(rear_down.bounding_box().min.Y, -47)
        self.assertAlmostEqual(rear_down.bounding_box().max.Y, 0)


if __name__ == '__main__':
    unittest.main()
