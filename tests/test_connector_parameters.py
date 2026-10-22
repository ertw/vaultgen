"""Independent dimensional edits must remain valid native mating features."""
from dataclasses import replace
import unittest

from vault.mating_features import (
    LowerClosedDovetailDimensions, LowerOpenDovetailDimensions,
    UpperOpenDovetailDimensions, UpperRailDimensions, TrackDimensions,
    lower_closed_end_dovetail, lower_open_end_dovetail,
    upper_open_end_dovetail, upper_outer_rail, upper_track_cutter,
)
from vault.hook_features import LowerHookDimensions, lower_outer_hook


class ConnectorParameterTests(unittest.TestCase):
    def test_hook_depth_and_setback_are_independent(self):
        dimensions = LowerHookDimensions()
        original = lower_outer_hook(dimensions)
        deeper = lower_outer_hook(replace(dimensions, crown_depth=dimensions.crown_depth+.1))
        shifted = lower_outer_hook(replace(dimensions, back_offset=dimensions.back_offset+1))
        for shape in (original, deeper, shifted):
            self.assertTrue(shape.is_valid)
            self.assertEqual(len(shape.solids()), 1)
        a, b, c = (shape.bounding_box() for shape in (original, deeper, shifted))
        self.assertAlmostEqual(a.min.Z-b.min.Z, .1, places=6)
        self.assertAlmostEqual(a.max.Z, b.max.Z, places=6)
        self.assertAlmostEqual(a.min.Y-c.min.Y, 1, places=6)
        self.assertAlmostEqual(a.max.Y-c.max.Y, 1, places=6)

    def test_height_edit_keeps_attachment_and_changes_crown(self):
        for builder, dimensions, upper in (
            (lower_closed_end_dovetail, LowerClosedDovetailDimensions(), False),
            (lower_open_end_dovetail, LowerOpenDovetailDimensions(), False),
            (upper_open_end_dovetail, UpperOpenDovetailDimensions(), True),
            (upper_outer_rail, UpperRailDimensions(), True),
        ):
            with self.subTest(feature=builder.__name__):
                nominal = builder(dimensions)
                edited = builder(replace(dimensions, height=dimensions.height+.1))
                self.assertTrue(edited.is_valid)
                self.assertEqual(len(edited.solids()), 1)
                original_bounds, edited_bounds = nominal.bounding_box(), edited.bounding_box()
                if upper:
                    self.assertAlmostEqual(edited_bounds.min.Z, original_bounds.min.Z, places=5)
                    self.assertAlmostEqual(edited_bounds.max.Z-original_bounds.max.Z, .1, places=5)
                else:
                    self.assertAlmostEqual(edited_bounds.max.Z, original_bounds.max.Z, places=5)
                    self.assertAlmostEqual(original_bounds.min.Z-edited_bounds.min.Z, .1, places=5)

    def test_shorter_rail_moves_open_end_and_keeps_closed_nose(self):
        long = upper_outer_rail(length=168.1214)
        short = upper_outer_rail(length=126.1214)
        self.assertTrue(short.is_valid)
        self.assertAlmostEqual(long.bounding_box().min.Y, short.bounding_box().min.Y, places=6)
        self.assertAlmostEqual(long.bounding_box().max.Y-short.bounding_box().max.Y, 42, places=6)
        self.assertTrue(long.is_inside((23,20,1)))
        self.assertTrue(short.is_inside((23,20,1)))
        self.assertFalse(long.is_inside((1,95,1)))
        self.assertTrue(short.is_inside((1,95,1)))

    def test_track_width_edit_preserves_center_floor(self):
        original = upper_track_cutter()
        narrower = upper_track_cutter(replace(TrackDimensions(), width=7.0))
        self.assertTrue(original.is_inside((3.6,0,-.1)))
        self.assertFalse(narrower.is_inside((3.6,0,-.1)))
        self.assertAlmostEqual(original.bounding_box().min.Z,narrower.bounding_box().min.Z,places=8)
        self.assertTrue(narrower.is_valid)

    def test_nonfinite_dimensions_are_rejected_before_geometry(self):
        for dimensions in (LowerClosedDovetailDimensions(), LowerOpenDovetailDimensions(),
                           UpperOpenDovetailDimensions(), UpperRailDimensions(), TrackDimensions()):
            field = 'depth' if isinstance(dimensions,TrackDimensions) else 'height'
            with self.subTest(feature=type(dimensions).__name__), self.assertRaises(ValueError):
                replace(dimensions,**{field:float('nan')})


if __name__ == '__main__':
    unittest.main()
