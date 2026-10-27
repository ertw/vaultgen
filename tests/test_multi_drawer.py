"""Native two-bay geometry and public part-selection regressions."""
from contextlib import redirect_stderr
from dataclasses import replace
from io import StringIO
import unittest
from unittest.mock import patch

from vault import __main__ as cli
from vault.drawer import DrawerLayout
from vault.model import build_module, print_orientation
from vault.shell import ShellDimensions
from vault.spec import ModuleSpec


class MultiDrawerSelectionTests(unittest.TestCase):
    def test_layout_is_explicit_and_keeps_legacy_names(self):
        single = ModuleSpec('L', 6, 2)
        double = replace(single, drawer_columns=2)
        self.assertEqual(single.slug, 'l6_module_2f')
        self.assertEqual(double.slug, 'l6_2_columns_module_2f')
        self.assertEqual(double.name, 'L6² Module 2F')
        self.assertEqual(double.drawer_centers, (-82.4, 82.4))
        self.assertEqual(double.width, single.width)
        self.assertEqual(double.bank_centers, single.bank_centers)
        self.assertEqual(DrawerLayout(double).spec.family, 'S')
        self.assertTrue(replace(double, module_rear=2).slug.endswith('_rear_2mm'))

    def test_matching_parts_reuse_s_drawer_identities(self):
        for part in ('box', 'facade', 'rails', 'runner_guides', 'runner_slides'):
            with self.subTest(part=part):
                self.assertEqual(cli.select_spec(part, 'L', 6, 2, drawer_columns=2),
                                 cli.select_spec(part, 'S', 6, 2))
        with patch.object(cli, 'build') as build:
            with patch('sys.argv', ['vault', 'build', '--family', 'L', '--depth-units', '6',
                                    '--height-units', '2', '--drawer-columns', '2']):
                cli.main()
            build.assert_called_once_with(cli.PROJECT_ROOT / 'out',
                                          ModuleSpec('L', 6, 2, drawer_columns=2))

    def test_invalid_layouts_are_rejected_before_construction(self):
        for family, columns in [('S', 2), ('M', 2), ('XL', 2), ('L', 0),
                                ('L', 3), ('L', True), ('L', 2.0)]:
            with self.subTest(family=family, columns=columns), self.assertRaises(ValueError):
                ModuleSpec(family, drawer_columns=columns)
        with patch.object(cli, 'build') as build, patch('sys.argv',
                ['vault', 'build', '--drawer-columns', '2']):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                cli.main()
            build.assert_not_called()

    def test_four_drawers_use_s1f_parts_and_shared_module_identity(self):
        spec = ModuleSpec('L', 6, 2, drawer_columns=2, drawer_rows=2)
        tall = replace(spec, drawer_rows=1)
        self.assertEqual(spec.slug, tall.slug)
        self.assertEqual(spec.name, tall.name)
        self.assertEqual(cli.select_spec('module', 'L', 6, 2, drawer_columns=2, drawer_rows=2), tall)
        self.assertEqual(spec.drawer_origins, ((-82.4, 0), (82.4, 0), (-82.4, 48), (82.4, 48)))
        self.assertEqual(DrawerLayout(spec).spec, ModuleSpec('S', 6, 1))
        for part in ('box', 'facade', 'rails', 'runner_guides', 'runner_slides'):
            self.assertEqual(cli.select_spec(part, 'L', 6, 2, drawer_columns=2, drawer_rows=2),
                             cli.select_spec(part, 'S', 6, 1))
        for changes in ({'family': 'S'}, {'drawer_columns': 1}, {'height_units': 1},
                        {'height_units': 4}, {'drawer_rows': True}, {'drawer_rows': 2.0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(spec, **changes)

    def test_direct_module_builds_share_configuration_hash_and_alias(self):
        with patch.object(cli, 'run_build') as run_build:
            for rows in (1, 2):
                cli.build(cli.PROJECT_ROOT / 'out',
                          ModuleSpec('L', 6, 2, drawer_columns=2, drawer_rows=rows))
        first, second = run_build.call_args_list
        self.assertEqual(first.args[:2], second.args[:2])
        self.assertEqual(first.kwargs, second.kwargs)
        self.assertEqual(second.kwargs['parameters']['drawer_rows'], 1)


class MultiDrawerGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = ModuleSpec('L', 6, 2, drawer_columns=2)
        cls.printable = build_module(cls.spec)
        cls.finished = build_module(cls.spec, include_supports=False)
        cls.four_drawers = build_module(replace(cls.spec, drawer_rows=2), include_supports=False)

    def test_one_connected_solid_and_closed_back_print_orientation(self):
        for shape in (self.printable, self.finished):
            self.assertTrue(shape.is_valid)
            self.assertEqual(len(shape.solids()), 1)
            self.assertEqual(len(shape.shells()), 1)
            self.assertAlmostEqual(shape.bounding_box().size.X, 329.6, places=5)
        self.assertAlmostEqual(print_orientation(self.printable).bounding_box().min.Z, 0, places=5)

    def test_two_open_cavities_and_shared_divider(self):
        for center in self.spec.drawer_centers:
            for z in (23.5, 47.5, 71.5):
                self.assertFalse(self.finished.is_inside((center, 100, z)))
            self.assertTrue(self.finished.is_inside((center, .8, 23.5)))
            self.assertFalse(self.finished.is_inside((center, 1, 23.5)))
        self.assertTrue(self.finished.is_inside((0, 100, 47.5)))
        self.assertTrue(self.finished.is_inside((0, 250, 23.5)))
        for x in (-7, 7):
            for z in (23.5, 71.5):
                self.assertFalse(self.finished.is_inside((x, 100, z)))

    def test_rear_access_reaches_center_stop_slots_on_each_tier(self):
        stop_y = self.spec.depth / 2 + ShellDimensions().stopper_center_offset
        for tier in self.spec.tier_offsets:
            z = 23.5009 + tier
            for y in (0.1, 50, stop_y):
                self.assertFalse(self.finished.is_inside((0, y, z)))
            self.assertTrue(self.finished.is_inside((2.5, 50, z)))
            self.assertFalse(self.finished.is_inside((0, 50, z + 3)))
            self.assertTrue(self.finished.is_inside((0, 50, z + 3.3)))
            self.assertTrue(self.finished.is_inside((0, stop_y + 8.5, z)))

    def test_mouth_handedness_and_removable_supports_repeat_in_each_bay(self):
        for center in self.spec.drawer_centers:
            for tier in self.spec.tier_offsets:
                y = self.spec.depth - 3.1
                for local_x, z, inside in ((-70.3344, 7.2, False),
                                            (70.3344, 7.2, True),
                                            (-70.3344, 39.8, True),
                                            (70.3344, 39.8, False)):
                    self.assertEqual(self.finished.is_inside((center + local_x, y, z + tier)), inside)
                for local_x, z in ((-70, 8.2), (70, 38.8)):
                    point = (center + local_x, y, z + tier)
                    self.assertTrue(self.printable.is_inside(point))
                    self.assertFalse(self.finished.is_inside(point))


    def test_both_layouts_have_identical_open_housing(self):
        self.assertTrue(self.four_drawers.is_valid)
        self.assertEqual(len(self.four_drawers.solids()), 1)
        self.assertEqual(len(self.four_drawers.shells()), 1)
        for first, second in ((self.finished, self.four_drawers), (self.four_drawers, self.finished)):
            difference = first.cut(second)
            self.assertLess(sum(abs(solid.volume) for solid in difference.solids()), 1e-5)
        for x in self.spec.drawer_centers:
            for z in (44.2, 47.5, 50.8):
                self.assertFalse(self.four_drawers.is_inside((x, 100, z)))
                self.assertTrue(self.four_drawers.is_inside((0, 100, z)))

    def test_outer_catches_and_handed_runner_mouths_remain(self):
        for x in self.spec.drawer_centers:
            for z in (2, self.spec.height - 2):
                self.assertFalse(self.four_drawers.is_inside((x, self.spec.depth - 7, z)))
                self.assertTrue(self.four_drawers.is_inside((x, self.spec.depth - 11, z)))
            for z in self.spec.tier_offsets:
                self.assertFalse(self.four_drawers.is_inside((x - 70.3344, self.spec.depth - 3.1, z + 7.2)))
                self.assertFalse(self.four_drawers.is_inside((x + 70.3344, self.spec.depth - 3.1, z + 39.8)))

    def test_four_drawer_shadow_gaps_preserve_inner_seating_lands(self):
        # Probe the short facade's rounded corners at the middle of the 2F
        # opening. These recesses must also exist behind a tall facade.
        for shape in (self.finished, self.four_drawers):
            for center in self.spec.drawer_centers:
                for side in (-1, 1):
                    for z in (44.048, 50.952):
                        x = center + side * 79.3
                        self.assertFalse(shape.is_inside((x, self.spec.depth - .25, z)))
                        self.assertTrue(shape.is_inside((x, self.spec.depth - .75, z)))
                        self.assertTrue(shape.is_inside((center + side * 77.5, self.spec.depth - .25, z)))


if __name__ == '__main__':
    unittest.main()
