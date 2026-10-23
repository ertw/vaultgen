"""Independent source dimensions and functional rail features."""

from dataclasses import replace
import unittest

from vault.geared_rails import D, GearRailDimensions, build_gear_rail


class GearRailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plain = build_gear_rail()
        cls.retained = build_gear_rail(retained=True)

    def test_native_parts_preserve_measured_envelope_and_volume(self):
        for name, shape, source_volume, back in (
            ("plain", self.plain, 1542.0897154, 0),
            ("retained", self.retained, 1819.7390565, -1.4187),
        ):
            with self.subTest(part=name):
                self.assertTrue(shape.is_valid)
                self.assertEqual(len(shape.solids()), 1)
                bounds = shape.bounding_box()
                for measured, expected in zip(
                    (bounds.min.X, bounds.max.X, bounds.min.Y, bounds.max.Y, bounds.min.Z, bounds.max.Z),
                    (0, 121.0537, back, 4.8, 0, 3.8),
                ):
                    self.assertAlmostEqual(measured, expected, delta=.001)
                self.assertLess(abs(shape.volume-source_volume)/source_volume, .001)

    def test_chamfered_section_and_rounded_rib(self):
        self.assertFalse(self.plain.is_inside((20, .2, .2)))
        self.assertTrue(self.plain.is_inside((20, 1.0, .2)))
        self.assertFalse(self.plain.is_inside((20, 4.6, 3.6)))
        self.assertTrue(self.plain.is_inside((20, 4.6, 1.9)))
        self.assertFalse(self.plain.is_inside((20, -.7, 1.9)))
        self.assertTrue(self.retained.is_inside((20, -.7, 1.9)))
        self.assertFalse(self.retained.is_inside((20, -1.3, .9)))
        self.assertFalse(self.retained.is_inside((5, -.7, 1.9)))

    def test_tooth_phase_and_root_depth_match_source_sections(self):
        # These are independently measured source valley centers. Later roots
        # catch accumulated errors from treating all intervals as one pitch.
        for x in (37.890, 41.8666, 45.8428, 81.9877, 89.9399, 114.0211):
            with self.subTest(x=x):
                self.assertFalse(self.plain.is_inside((x, 2.01, 1.9)))
                self.assertTrue(self.plain.is_inside((x, 1.88, 1.9)))
        # A narrow source valley leaves this material where a regular-width
        # valley would remove it; tooth engagement depends on retaining it.
        self.assertTrue(self.plain.is_inside((42.90, 3.0, 1.9)))
        self.assertFalse(self.plain.is_inside((42.84, 3.0, 1.9)))

    def test_tail_has_source_planar_ramp(self):
        self.assertTrue(self.plain.is_inside((119, 1.3, 2.50)))
        self.assertFalse(self.plain.is_inside((119, 1.3, 2.60)))
        self.assertFalse(self.plain.is_inside((.1, .3, 1.9)))
        self.assertTrue(self.plain.is_inside((.1, 2.4, 1.9)))

    def test_print_fit_dimensions_are_editable(self):
        edited = build_gear_rail(dimensions=replace(D, width=4.7, thickness=3.7))
        self.assertTrue(edited.is_valid)
        self.assertAlmostEqual(edited.bounding_box().max.Y, 4.7, places=5)
        self.assertAlmostEqual(edited.bounding_box().max.Z, 3.7, places=5)
        self.assertTrue(self.plain.is_inside((20, 4.75, 1.9)))
        self.assertFalse(edited.is_inside((20, 4.75, 1.9)))

    def test_invalid_parameters_are_rejected(self):
        for changes in ({"width": float("nan")}, {"edge_bevel": 2},
                        {"tooth_count": 0}, {"narrow_valleys": (1, 1)},
                        {"root_radius": 2}, {"retaining_start": 30},
                        {"tail_taper_slope": 10}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(GearRailDimensions(), **changes)


if __name__ == "__main__":
    unittest.main()
