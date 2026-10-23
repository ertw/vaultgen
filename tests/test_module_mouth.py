"""Assembled handedness and removable support under the runner-mouth ledges."""
from dataclasses import replace
import unittest

from vault.shell import (
    ShellDimensions, POCKET_LEDGE_HEIGHT, _mouth_supports, build_shell,
)
from vault.spec import DEFAULT_SPEC, ModuleSpec


class ModuleMouthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dimensions = ShellDimensions()
        cls.finished = build_shell(dimensions=replace(cls.dimensions, pocket_support_thickness=0))
        cls.printable = build_shell(dimensions=cls.dimensions)

    def test_finished_mates_share_the_box_exit_diagonal(self):
        for x, z, open_ in ((-70.3344, 8, True), (70.3344, 39, True),
                            (70.3344, 8, False), (-70.3344, 39, False)):
            with self.subTest(x=x, z=z):
                self.assertEqual(self.finished.is_inside((x, 185, z)), not open_)

    def test_supports_are_connected_and_preserve_outer_dimensions(self):
        self.assertTrue(self.printable.is_valid)
        self.assertEqual(len(self.printable.solids()), 1)
        self.assertEqual(len(self.printable.shells()), 1)
        self.assertGreater(self.printable.volume, self.finished.volume)
        for axis in ('X', 'Y', 'Z'):
            for end in ('min', 'max'):
                self.assertAlmostEqual(
                    getattr(getattr(self.printable.bounding_box(), end), axis),
                    getattr(getattr(self.finished.bounding_box(), end), axis), places=6,
                )

    def test_web_grows_from_rear_wall_and_only_teeth_touch_front_ledge(self):
        d, spec = self.dimensions, DEFAULT_SPEC
        inner = spec.half_width - d.channel_inner_inset
        ledge = spec.depth - d.pocket_front_offset
        back = ledge - d.pocket_length
        z = d.pocket_floor + POCKET_LEDGE_HEIGHT - .15 - d.pocket_support_thickness / 2
        for upper in (False, True):
            def point(x, y, height=z):
                return (x if upper else -x, y, 47 - height if upper else height)
            with self.subTest(upper=upper):
                # The web's first print layers overlap an already-solid wall.
                self.assertTrue(self.finished.is_inside(point(72, back - .01)))
                self.assertTrue(self.printable.is_inside(point(72, back + 2)))
                self.assertFalse(self.finished.is_inside(point(72, back + 2)))
                # Only narrow teeth cross the last .3 mm to the overhang.
                self.assertTrue(self.printable.is_inside(point(inner, ledge - .15)))
                self.assertFalse(self.printable.is_inside(point(72, ledge - .15)))
                self.assertTrue(self.finished.is_inside(point(inner, ledge + .01)))
                # A void remains below the web so it is removable from the mouth.
                self.assertFalse(self.printable.is_inside(point(72, back + 2, d.pocket_floor + .3)))

    def test_supports_follow_depth_floor_and_tiers_and_can_be_disabled(self):
        spec = ModuleSpec('S', 3, 2)
        d = replace(self.dimensions, pocket_floor=self.dimensions.pocket_floor + .2)
        parts = [part for tier in spec.tier_offsets for part in _mouth_supports(spec, d, tier)]
        self.assertEqual(len(parts), 4)
        for index, part in enumerate(parts):
            bounds = part.bounding_box()
            self.assertAlmostEqual(bounds.min.Y, spec.depth - d.pocket_front_offset - d.pocket_length - .02)
            self.assertAlmostEqual(bounds.max.Y, spec.depth - d.pocket_front_offset + .02)
            nominal = _mouth_supports(DEFAULT_SPEC, self.dimensions, 0)[index % 2].bounding_box()
            expected_shift = (index // 2) * 48 + (-.2 if index % 2 else .2)
            self.assertAlmostEqual(bounds.min.Z - nominal.min.Z, expected_shift)
        self.assertEqual(_mouth_supports(spec, replace(d, pocket_support_thickness=0), 0), [])


if __name__ == '__main__':
    unittest.main()
