"""The two rail variants export separately without relaxing single-part checks."""
from contextlib import redirect_stderr
from dataclasses import asdict
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build123d import Compound, Solid, import_step
from vault import __main__ as cli
from vault.geared_rails import D, SPEC


class GearedRailBuildTests(unittest.TestCase):
    def test_cli_and_catalog_preview_select_the_rail_set(self):
        with patch.object(cli, 'build') as build:
            with patch('sys.argv', ['vault', 'build', '--part', 'rails']):
                cli.main()
            build.assert_called_once_with(cli.PROJECT_ROOT / 'out', SPEC)
            self.assertEqual(cli.part_kind(SPEC), 'rail')
            build.reset_mock()
            cli.build_preview(SPEC.slug)
            build.assert_called_once_with(cli.PROJECT_ROOT / 'out', SPEC)

    def test_rails_reject_unsupported_sizes_before_building(self):
        with patch.object(cli, 'build') as build:
            with patch('sys.argv', ['vault', 'build', '--part', 'rails', '--family', 'XL']):
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                    cli.main()
            self.assertEqual(error.exception.code, 2)
            build.assert_not_called()

    def test_saved_parameters_include_rail_dimensions(self):
        with patch.object(cli, 'run_build') as transaction:
            cli.build(Path('/tmp/vault-rail-parameters'), SPEC)
        configuration = transaction.call_args.kwargs['parameters']
        self.assertEqual(configuration['part'], SPEC.slug)
        self.assertEqual(configuration['geared_rails'], asdict(D))
        self.assertEqual(transaction.call_args.kwargs['aliases'], ['latest/s_geared_rails'])

    def test_each_variant_has_checked_step_and_printable_stl(self):
        # Small stand-ins exercise the real export/round-trip path quickly.
        def rail(retained=False):
            return Solid.make_box(12, 6 if retained else 4, 3).translate((0, -2, 1))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('vault.geared_rails.build_gear_rail', side_effect=rail):
                with patch('vault.render.render_review'):
                    manifest, viewer = cli._export_rails(root)
            self.assertTrue(manifest['step_roundtrip']['passed'])
            self.assertEqual(manifest['solids'], 2)
            self.assertEqual({p['name'] for p in viewer['components']},
                             {'s_geared_rail_plain', 's_geared_rail_retained'})
            assembly = import_step(root / viewer['assembly'])
            self.assertEqual(len(assembly.solids()), 2)
            self.assertEqual({child.label for child in assembly.children},
                             {'s_geared_rail_plain', 's_geared_rail_retained'})
            for name, report in manifest['parts'].items():
                self.assertEqual(report['solids'], 1)
                self.assertEqual(report['boundary_shells'], 1)
                self.assertTrue(report['step_roundtrip']['passed'])
                self.assertTrue(report['print_step_roundtrip']['passed'])
                self.assertTrue(report['stl_watertight'])
                self.assertTrue(report['stl_winding_consistent'])
                printable = import_step(root / f'{name}_print.step')
                self.assertAlmostEqual(printable.bounding_box().min.Z, 0., places=6)
                self.assertTrue((root / 'stl' / f'{name}.stl').is_file())

    def test_disconnected_rail_is_rejected_before_export(self):
        disconnected = Compound(children=[Solid.make_box(12, 4, 3),
                                           Solid.make_box(12, 4, 3).translate((0, 6, 0))])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('vault.geared_rails.build_gear_rail', return_value=disconnected):
                with self.assertRaisesRegex(ValueError, 'one valid solid'):
                    cli._export_rails(root)
            self.assertFalse(list(root.glob('*.step')))


if __name__ == '__main__':
    unittest.main()
