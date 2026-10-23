"""Printed variants retain distinct build identities and bed placement."""
from contextlib import redirect_stderr
from dataclasses import asdict
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vault import __main__ as cli
from vault.printed_joint import BOX_SPEC, FACADE_SPEC, SCREW_SPEC


class PrintedJointBuildTests(unittest.TestCase):
    def test_cli_and_catalog_preview_select_the_same_part(self):
        for selector, spec, kind in [('box-printed-screw', BOX_SPEC, 'box'),
                                     ('facade-printed-screw', FACADE_SPEC, 'facade'),
                                     ('screw', SCREW_SPEC, 'screw')]:
            with self.subTest(part=selector), patch.object(cli, 'build') as build:
                with patch('sys.argv', ['vault', 'build', '--part', selector]):
                    cli.main()
                build.assert_called_once_with(cli.PROJECT_ROOT / 'out', spec)
                self.assertEqual(cli.part_kind(spec), kind)
                build.reset_mock()
                cli.build_preview(spec.slug)
                build.assert_called_once_with(cli.PROJECT_ROOT / 'out', spec)

    def test_printed_variant_rejects_unsupported_sizes_before_building(self):
        for selector in ('box-printed-screw', 'facade-printed-screw', 'screw'):
            with self.subTest(part=selector), patch.object(cli, 'build') as build:
                with patch('sys.argv', ['vault', 'build', '--part', selector, '--family', 'M']):
                    with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                        cli.main()
                self.assertEqual(error.exception.code, 2)
                build.assert_not_called()

    def test_catalog_preview_dispatches_to_the_printed_constructor(self):
        from vault import printed_joint
        for spec, constructor in [(BOX_SPEC, 'build_printed_box'),
                                  (FACADE_SPEC, 'build_printed_facade'),
                                  (SCREW_SPEC, 'build_printed_screw')]:
            with self.subTest(part=spec.slug), tempfile.TemporaryDirectory() as temporary:
                with patch.object(printed_joint, constructor) as make_part:
                    with patch.object(cli, '_export_into') as export:
                        cli._build_into(Path(temporary), spec)
                make_part.assert_called_once_with()
                self.assertIs(export.call_args.args[0], make_part.return_value)
                self.assertEqual(export.call_args.args[3], spec)

    def test_screw_export_places_the_head_on_the_plate_and_tip_upward(self):
        from build123d import Plane, Solid
        # Head extends behind Y=0; shaft points in +Y in assembly coordinates.
        head = Solid.make_cylinder(6, 4, Plane(origin=(0, -4, 0), z_dir=(0, 1, 0)))
        shaft = Solid.make_cylinder(3, 8, Plane(origin=(0, 0, 0), z_dir=(0, 1, 0)))
        screw = head.fuse(shaft)
        printable = cli.print_orientation(screw, SCREW_SPEC)
        self.assertAlmostEqual(printable.bounding_box().min.Z, 0, places=6)
        self.assertAlmostEqual(printable.bounding_box().max.Z, 12, places=6)
        self.assertTrue(printable.is_inside((5, 0, 2)))
        self.assertFalse(printable.is_inside((5, 0, 10)))
        self.assertTrue(printable.is_inside((2, 0, 10)))
        self.assertAlmostEqual(printable.volume, screw.volume, places=5)

    def test_saved_parameters_include_joint_fit_and_facade_shadow_gap(self):
        from vault.printed_joint import D
        from vault.shadow_gap import DEFAULT_GAP
        for spec in (BOX_SPEC, FACADE_SPEC, SCREW_SPEC):
            with self.subTest(part=spec.slug), patch.object(cli, 'run_build') as transaction:
                cli.build(Path('/tmp/vault-printed-joint-parameters'), spec)
                configuration = transaction.call_args.kwargs['parameters']
                self.assertEqual(configuration['part'], spec.slug)
                self.assertEqual(configuration['printed_joint'], asdict(D))
                if spec == FACADE_SPEC:
                    self.assertEqual(configuration['shadow_gap'], asdict(DEFAULT_GAP))
                else:
                    self.assertNotIn('shadow_gap', configuration)

    def test_printed_facade_rear_pilots_are_seated_on_the_plate(self):
        from build123d import Plane, Solid
        rear_face = Solid.make_box(30, 5, 20, Plane(origin=(-15, 0, 0)))
        pilot = Solid.make_cylinder(4, 2.1, Plane(origin=(0, -2, 10), z_dir=(0, 1, 0)))
        facade = rear_face.fuse(pilot)
        printable = cli.print_orientation(facade, FACADE_SPEC)
        self.assertAlmostEqual(printable.bounding_box().min.Z, 0, places=6)
        self.assertAlmostEqual(printable.bounding_box().max.Z, 7, places=6)
        self.assertTrue(printable.is_inside((0, -10, 1)))
        self.assertFalse(printable.is_inside((10, -10, 1)))
        self.assertTrue(printable.is_inside((10, -10, 3)))
        self.assertAlmostEqual(printable.volume, facade.volume, places=5)


if __name__ == '__main__':
    unittest.main()
