"""The thin facade changes rear pockets while retaining its loaded interfaces."""
import math
import unittest

from build123d import Plane, Solid

from vault.drawer import DrawerLayout
from vault.facade import FacadeSpec, build_facade


class FacadeFloorSpecTests(unittest.TestCase):
    def test_legacy_identity_and_distinct_thin_identity(self):
        self.assertEqual(FacadeSpec('M', 2).slug, 'm2f_facade')
        self.assertEqual(FacadeSpec('M', 2).name, 'M2F Facade')
        self.assertEqual(FacadeSpec('M', 2, .8).slug, 'm2f_facade_floor_0p8')
        self.assertIn('0.8 mm floor', FacadeSpec('M', 2, .8).name)

    def test_floor_validation(self):
        for value in (0, .9, 3, '0.8', None, True, [], {}, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                FacadeSpec(facade_floor=value)


class FacadeShellGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {}
        for family in ('S', 'M', 'L'):
            for height in (1, 2):
                spec = FacadeSpec(family, height, .8)
                baseline = build_facade(spec=FacadeSpec(family, height))
                thin = build_facade(spec=spec)
                cls.cases[family, height] = (spec, baseline, thin, baseline.cut(thin))

    def test_valid_connected_solids_and_unchanged_bounds(self):
        for case, (_, baseline, thin, _) in self.cases.items():
            with self.subTest(case=case):
                self.assertTrue(thin.is_valid)
                self.assertEqual(len(thin.solids()), 1)
                self.assertEqual(len(thin.shells()), 1)
                for actual, expected in zip(thin.bounding_box().min,
                                            baseline.bounding_box().min):
                    self.assertAlmostEqual(actual, expected, places=5)
                for actual, expected in zip(thin.bounding_box().max,
                                            baseline.bounding_box().max):
                    self.assertAlmostEqual(actual, expected, places=5)

    def test_subtractive_material_reduction(self):
        for case, (_, baseline, thin, removed) in self.cases.items():
            with self.subTest(case=case):
                self.assertLess(thin.volume, .85 * baseline.volume)
                self.assertAlmostEqual(removed.volume + thin.volume, baseline.volume,
                                       delta=baseline.volume * 3e-6)
                self.assertLess(sum(s.volume for s in thin.cut(baseline).solids()), .001)
                # No removed material reaches the original flat front surface.
                self.assertLessEqual(removed.bounding_box().max.Y, 9.200001)

    def test_actual_floor_under_front_and_recess(self):
        for case, (_, baseline, thin, _) in self.cases.items():
            with self.subTest(case=case):
                # Two independent front datums need different pocket depths.
                for x, z, front_y in ((-35, 13, 10), (39, 15, 7.91)):
                    self.assertTrue(baseline.is_inside((x, front_y - .81, z)))
                    self.assertFalse(thin.is_inside((x, front_y - .81, z)))
                    self.assertTrue(thin.is_inside((x, front_y - .79, z)))
                    self.assertTrue(thin.is_inside((x, front_y - .01, z)))
                    self.assertFalse(thin.is_inside((x, front_y + .01, z)))
                    # A rear-open cavity has no retained ceiling behind its skin.
                    for y in (.1, 1, 3, 5, 6):
                        self.assertFalse(thin.is_inside((x, y, z)))
                if case[1] == 2:
                    self.assertFalse(thin.is_inside((0, 9.19, 65)))
                    self.assertTrue(thin.is_inside((0, 9.21, 65)))

    def test_lock_and_all_screw_bands_are_unchanged(self):
        for case, (spec, baseline, thin, removed) in self.cases.items():
            with self.subTest(case=case):
                # Independently require at least 3 mm beyond the largest lock
                # lobe and screw risers throughout their entire axial depth.
                masks = [Solid.make_cylinder(23.125, 10.2,
                         Plane(origin=(-.01, -.1, 23.694), z_dir=(0, 1, 0)))]
                for x, z in DrawerLayout(spec).screw_positions:
                    masks.append(Solid.make_cylinder(9.8, 10.2,
                                 Plane(origin=(x, -.1, z), z_dir=(0, 1, 0))))
                    self.assertFalse(thin.is_inside((x, 3, z)))
                    self.assertTrue(thin.is_inside((x + 3, 3, z)))
                    self.assertFalse(thin.is_inside((x + 3, 6, z)))
                for mask in masks:
                    self.assertLess(sum(s.volume for s in removed.intersect(mask) or []), .001)

    def test_edge_seating_and_rebate_are_unchanged(self):
        for case, (spec, baseline, thin, removed) in self.cases.items():
            with self.subTest(case=case):
                layout = DrawerLayout(spec)
                for z in (.5, layout.spec.height - .5):
                    self.assertFalse(thin.is_inside((0, .25, z)))
                    self.assertTrue(thin.is_inside((0, .75, z)))
                # The full rear seating plane retains its original material.
                seat = Solid.make_box(layout.spec.width + 2, .79,
                                      layout.spec.height + 2,
                                      Plane(origin=(-layout.spec.half_width - 1, 0, -1)))
                self.assertLess(sum(s.volume for s in removed.intersect(seat) or []), .001)


if __name__ == '__main__':
    unittest.main()
