"""Runner selection and publication use the same checked export path as rails."""
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build123d import Solid, import_step

from vault import __main__ as cli


class RunnerBuildTests(unittest.TestCase):
    def test_depth_selects_shared_runner_geometry_across_families_and_heights(self):
        for kind in ('runner_guides', 'runner_slides'):
            for depth in range(3, 8):
                expected = cli.select_spec(kind, 'S', depth, 1)
                self.assertEqual(expected.slug, f'x{depth}_{kind}')
                self.assertEqual(cli.part_kind(expected), kind)
                for family in ('S', 'M', 'L'):
                    for height in (1, 2):
                        self.assertEqual(cli.select_spec(kind, family, depth, height), expected)
            with patch.object(cli, 'build') as build:
                with patch('sys.argv', ['vault', 'build', '--part', kind,
                                        '--family', 'L', '--depth-units', '7', '--height-units', '2']):
                    cli.main()
                build.assert_called_once_with(cli.PROJECT_ROOT / 'out', cli.select_spec(kind, 'L', 7, 2))

    def test_unsupported_runner_sizes_fail_before_building(self):
        for kind in ('runner_guides', 'runner_slides'):
            for option, value in (('--family', 'XL'), ('--depth-units', '8'), ('--height-units', '4')):
                with self.subTest(kind=kind, option=option), patch.object(cli, 'build') as build:
                    with patch('sys.argv', ['vault', 'build', '--part', kind, option, value]):
                        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                            cli.main()
                    self.assertEqual(error.exception.code, 2)
                    build.assert_not_called()

    def test_both_runner_pairs_export_separate_checked_files_and_assembly(self):
        for kind in ('runner_guides', 'runner_slides'):
            spec = cli.select_spec(kind, 'M', 5, 2)
            solid = Solid.make_box(9, 20, 3).translate((0, 0, 2))
            pair = {'left': solid, 'right': solid.moved(solid.location)}
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with patch(f'vault.{kind}.build_{kind}', return_value=pair), patch('vault.render.render_review'):
                    manifest, viewer = cli._export_runners(root, spec)
                self.assertTrue(manifest['step_roundtrip']['passed'])
                self.assertEqual(len(import_step(root / viewer['assembly']).solids()), 2)
                self.assertEqual(set(manifest['parts']), {f'{spec.slug}_{side}' for side in pair})
                for name, report in manifest['parts'].items():
                    self.assertEqual(report['kind'], kind)
                    preview = report['assembly_mesh']
                    self.assertTrue(preview['finished'])
                    self.assertEqual(preview['component'], name.rsplit('_', 1)[-1])
                    expected_min = pair[preview['component']].bounding_box().min
                    self.assertEqual(preview['print_to_native'][12:15], list(expected_min))
                    native = import_step(root / preview['step_path'])
                    self.assertAlmostEqual(native.bounding_box().min.Z, expected_min.Z, places=6)
                    self.assertTrue((root / preview['path']).is_file())
                    self.assertTrue(report['step_roundtrip']['passed'])
                    self.assertTrue(report['print_step_roundtrip']['passed'])
                    self.assertTrue(report['stl_watertight'])
                    self.assertAlmostEqual(import_step(root / f'{name}_print.step').bounding_box().min.Z, 0., places=6)
                    self.assertTrue((root / 'stl' / f'{name}.stl').is_file())
                with patch.object(cli, 'run_build') as transaction:
                    cli.build(root, spec)
                self.assertEqual(transaction.call_args.kwargs['parameters'],
                                 {'depth_units': 5, 'part': spec.slug})


if __name__ == '__main__':
    unittest.main()
