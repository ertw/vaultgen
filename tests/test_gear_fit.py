"""Geared-rail clearance through complete insertion and locking sweeps."""
from dataclasses import replace
import unittest

from vault.box import build_box
from vault.geared_rails import build_gear_rail
from vault.shell import ShellDimensions, build_shell
from tools.check_geared_rails import common_volume, place_gear_rail, swept_rail_envelope


class GearFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.standard = build_box()
        cls.module = build_shell(dimensions=replace(ShellDimensions(), pocket_support_thickness=0))

    def test_full_lateral_insertion_clears_box(self):
        # Each envelope contains every position of the whole rail along a
        # 134 mm insertion path, including the rib. It conservatively fills
        # the teeth, rounded ends, rib ramps, and tip ramp.
        for upper in (True, False):
            swept = swept_rail_envelope(upper, travel=134, limited_tail=False)
            self.assertTrue(swept.is_valid)
            with self.subTest(upper=upper):
                self.assertGreaterEqual(swept.distance_to(self.standard), .1969)

    def test_complete_twenty_mm_locking_sweep_clears_finished_module(self):
        for upper in (True, False):
            swept = swept_rail_envelope(upper, travel=20, limited_tail=True)
            with self.subTest(upper=upper):
                self.assertTrue(swept.is_valid)
                self.assertGreaterEqual(swept.distance_to(self.module), .18)

    def test_one_mm_overtravel_reaches_module_stop(self):
        # A positive control proves this check can detect entering the stop;
        # 21 mm is beyond the qualified travel and is not an insertion path.
        for upper in (True, False):
            rail = place_gear_rail(build_gear_rail(upper), upper, travel=21)
            with self.subTest(upper=upper):
                self.assertGreater(common_volume(rail, self.module), .01)

    def test_conservative_envelope_contains_actual_rail_geometry(self):
        for upper in (True, False):
            rail = build_gear_rail(upper)
            swept = swept_rail_envelope(upper, travel=20, limited_tail=True)
            for travel in (0, 10, 20):
                with self.subTest(upper=upper, travel=travel):
                    outside = place_gear_rail(rail, upper, travel).cut(swept)
                    volume = 0.0 if outside is None else sum(s.volume for s in outside.solids())
                    self.assertLess(volume, 1e-5)
