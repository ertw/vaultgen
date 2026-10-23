"""Geometric regressions for size placement and independent fit controls."""
from dataclasses import replace
import unittest

from vault.shell import ShellDimensions, build_shell
from vault.spec import ModuleSpec


class ParametricSleeveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nominal = build_shell()
        cls.short_tall = build_shell(ModuleSpec("S", 3, 2))

    def test_shorter_box_stop_follows_measured_midpoint_rule(self):
        # S3 source section: center Y=101.549 mm. Anchoring to the front
        # instead would incorrectly put this slot at Y=80.55 mm.
        self.assertFalse(self.short_tall.is_inside((81.8, 101.55, 23.5)))
        self.assertTrue(self.short_tall.is_inside((81.8, 80.55, 23.5)))

    def test_tall_box_repeats_runner_instead_of_stretching_it(self):
        # Both channels remain 28 mm tall, with solid side support between.
        self.assertFalse(self.short_tall.is_inside((75, 40, 23.5)))
        self.assertFalse(self.short_tall.is_inside((75, 40, 71.5)))
        self.assertTrue(self.short_tall.is_inside((75, 40, 47)))
        self.assertTrue(self.short_tall.is_valid)
        self.assertEqual(len(self.short_tall.solids()), 1)
        self.assertEqual(len(self.short_tall.shells()), 1)

    def test_bore_fit_edit_changes_clearance_without_moving_axis(self):
        wider = build_shell(dimensions=replace(ShellDimensions(), bore_radius=1.9))
        # Between nominal R1.8 and edited R1.9, away from the entry taper.
        probe = (76.0957, 50, 4.753513)
        self.assertTrue(self.nominal.is_inside(probe))
        self.assertFalse(wider.is_inside(probe))
        self.assertTrue(wider.is_valid)
        self.assertLess(wider.volume, self.nominal.volume)

    def test_diagonal_mouth_relief_matches_assembled_geared_rails(self):
        # A proper source rotation places the lower mate at -X and upper at
        # +X, matching the box exits. Probe clear of the sacrificial webs.
        self.assertTrue(self.nominal.is_inside((70.3344, 185, 7.2)))
        self.assertFalse(self.nominal.is_inside((-70.3344, 185, 7.2)))
        self.assertFalse(self.nominal.is_inside((70.3344, 185, 39.8)))
        self.assertTrue(self.nominal.is_inside((-70.3344, 185, 39.8)))


if __name__ == "__main__":
    unittest.main()
