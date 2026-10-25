"""Geared-rail clearance through complete insertion and locking sweeps."""
from dataclasses import replace
import unittest

from vault.box import build_box
from vault.geared_rails import GearRailSpec, build_gear_rail
from vault.spec import ModuleSpec
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


class UnlockedRailStopTests(unittest.TestCase):
    def test_family_rails_seat_at_the_s4_unlocked_stop(self):
        # Different depths/heights must preserve the lock's tooth registration.
        # Include the reported L6 2F failure and both heights of every family.
        for family in ('S', 'M', 'L'):
            rails = {upper: build_gear_rail(upper, spec=GearRailSpec(family))
                     for upper in (False, True)}
            for depth, height in ((3, 1), (6, 2)):
                spec = ModuleSpec(family, depth, height)
                box = build_box(spec=spec)
                for upper, rail in rails.items():
                    def placed(travel):
                        return place_gear_rail(rail, upper, travel).translate(
                            (0, spec.depth - 188.1, 0))

                    with self.subTest(family=family, height=height, upper=upper):
                        # The existing clearance pose is 0.2 mm off the stop.
                        # Seating it must produce contact without penetration;
                        # another 0.1 mm inward must hit solid material.
                        seated = placed(-.2)
                        self.assertLess(seated.distance_to(box), 1e-5)
                        self.assertLess(common_volume(seated, box), 1e-5)
                        self.assertGreater(common_volume(placed(-.3), box), .01)
                        # This also catches prematurely blocking the outgoing
                        # extended tail or the retained upper rail's rib.
                        for travel in (0, 10, 20):
                            moving = placed(travel)
                            self.assertGreater(moving.distance_to(box), .19)
                            self.assertLess(common_volume(moving, box), 1e-5)
