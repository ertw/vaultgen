"""Tray integrity, attachment datums, runner clearance, and print placement."""
import unittest
from vault.box import SPEC, build_box, print_orientation


class BoxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box = build_box()

    def test_single_solid_and_envelope(self):
        self.assertTrue(self.box.is_valid)
        self.assertEqual(len(self.box.solids()), 1)
        self.assertEqual(len(self.box.shells()), 1)
        for actual, expected in zip(self.box.bounding_box().size, (134.2,185.8,37.5)):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertAlmostEqual(self.box.bounding_box().max.Y,188.1,places=5)
        self.assertEqual(SPEC.slug, 's4_box_1f')

    def test_open_tray_and_facade_attachment(self):
        self.assertTrue(self.box.is_inside((0,80,6)))
        self.assertFalse(self.box.is_inside((0,80,15)))
        self.assertFalse(self.box.is_inside((0,186,23.5)))
        for x in (-51.45,51.45):
            self.assertFalse(self.box.is_inside((x,183,23.5)))
            self.assertTrue(self.box.is_inside((x+3,183,23.5)))
            self.assertFalse(self.box.is_inside((x,3.5,23.5)))

    def test_runner_channels_and_print_bed(self):
        for sign in (-1,1):
            self.assertFalse(self.box.is_inside((sign*65.4,80,23.5)))
            self.assertTrue(self.box.is_inside((sign*66.15,80,23.5)))
        printed=print_orientation(self.box)
        self.assertAlmostEqual(printed.bounding_box().min.Z,0,places=6)
        self.assertAlmostEqual(printed.volume,self.box.volume,places=5)
