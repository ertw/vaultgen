"""Seating lands and rebate direction are independent of appearance checks."""
import unittest
from vault.facade import build_facade
from vault.shadow_gap import ShadowGap, perimeter_rebate
from vault.shell import build_shell
from vault.spec import DEFAULT_SPEC

class FacadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facade = build_facade()
        cls.module = perimeter_rebate(build_shell(), DEFAULT_SPEC.depth, -1)

    def test_valid_connected_facade(self):
        self.assertTrue(self.facade.is_valid)
        self.assertEqual(len(self.facade.solids()), 1)
        self.assertEqual(len(self.facade.shells()), 1)

    def test_matching_rebates_preserve_inner_seating_lands(self):
        for part, y, interior in [(self.facade,.25,.75), (self.module,187.85,187.35)]:
            for z in [.5,46.5]:
                self.assertFalse(part.is_inside((0,y,z)))
                self.assertTrue(part.is_inside((0,interior,z)))
            for z in [1.5,45.5]:
                self.assertTrue(part.is_inside((0,y,z)))

    def test_screw_axes_and_finger_opening_remain_clear(self):
        for x in [-51.45,51.45]:
            self.assertFalse(self.facade.is_inside((x,3,23.5)))
            self.assertTrue(self.facade.is_inside((x+3,3,23.5)))
            self.assertFalse(self.facade.is_inside((x+3,6,23.5)))
        self.assertFalse(self.facade.is_inside((0,5,23.5)))
        self.assertFalse(self.facade.is_inside((0,9,23.5)))

    def test_invalid_gap_rejected(self):
        for depth,width in [(0,1),(.5,0),(2,1),(.5,2),(float('nan'),1)]:
            with self.assertRaises(ValueError): ShadowGap(depth,width)
