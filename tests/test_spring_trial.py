"""Geometric contract for the isolated full-boss clearance experiment."""
import unittest

from build123d import Compound, Plane, Solid

from vault.accessories import build_spring
from vault.spring_trial import (
    BOSS_CENTER_X, BOSS_CENTER_Y, BOSS_RADIUS,
    build_spring_trial, flexible_region,
)


def volume(shape):
    if shape is None:
        return 0
    if isinstance(shape, list):
        return sum(volume(part) for part in shape)
    return sum(solid.volume for solid in shape.solids())


class SpringTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.standard = build_spring()
        cls.trial = build_spring_trial()
        cls.boss = Solid.make_cylinder(
            BOSS_RADIUS, 8, Plane(origin=(BOSS_CENTER_X, BOSS_CENTER_Y, -1)),
        )

    def test_continuous_solid_keeps_print_envelope_and_flat_bed(self):
        self.assertTrue(self.trial.is_valid)
        self.assertEqual(len(self.trial.solids()), 1)
        self.assertEqual(len(self.trial.shells()), 1)
        for actual, expected in zip(self.trial.bounding_box().min, self.standard.bounding_box().min):
            self.assertAlmostEqual(actual, expected, places=6)
        for actual, expected in zip(self.trial.bounding_box().max, self.standard.bounding_box().max):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertAlmostEqual(self.trial.bounding_box().min.Z, 0, places=7)
        self.assertLess(self.trial.volume, self.standard.volume)

    def test_fork_and_contact_end_are_unchanged(self):
        # Compare complete retained regions, including the thickness ramp,
        # rather than a few outline points or only the circular notch radius.
        for origin, width in (((9.283, -25, -1), 20), ((-30, -25, -1), 17.708)):
            region = Solid.make_box(width, 50, 10, Plane(origin=origin))
            original = Compound(self.standard.intersect(region))
            retained = Compound(self.trial.intersect(region))
            self.assertLess(volume(original.cut(retained)), 1e-6)
            self.assertLess(volume(retained.cut(original)), 1e-6)

    def test_fork_adjacent_loop_is_omitted_and_lower_load_path_retained(self):
        for point in ((4, 0, .5), (1.083, 16, .5), (-2, 0, .5)):
            self.assertTrue(self.standard.is_inside(point))
            self.assertFalse(self.trial.is_inside(point))
        # Remaining tall loop and new bridge both remain solid.
        for point in ((-8, 0, .5), (-11.167, 16, .5), (0, -16, .5), (8, -16, .5)):
            self.assertTrue(self.trial.is_inside(point))

    def test_full_boss_does_not_overlap_and_flexure_has_room(self):
        self.assertLess(volume(self.trial.intersect(self.boss)), 1e-6)
        # The original fork remains nominally close to the boss. Separately
        # measure the moving strip, including its new lower connection.
        self.assertGreater(self.trial.distance_to(self.boss), 0)
        self.assertLess(self.trial.distance_to(self.boss), .01)
        self.assertLess(flexible_region(self.standard).distance_to(self.boss), .25)
        self.assertGreater(flexible_region(self.trial).distance_to(self.boss), 6)


if __name__ == '__main__':
    unittest.main()
