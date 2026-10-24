"""Source dimensions and mechanism preservation for all printable rail families."""
from dataclasses import replace
import unittest

from vault.geared_rails import D, GearRailSpec, build_gear_rail, rail_dimensions


class RailFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = {
            (family, retained): build_gear_rail(retained, spec=GearRailSpec(family))
            for family in ("M", "L") for retained in (False, True)
        }

    def test_source_lengths_volumes_and_print_orientation(self):
        # Measurements come from the two disconnected solids of each supplied
        # family STL, independently of the analytic size-placement formulas.
        references = {
            "M": (165.6533203125, 2293.5932979219, 2571.2343458675),
            "L": (203.4533691406, 2935.0365755307, 3212.7031394703),
        }
        for family, (length, plain_volume, retained_volume) in references.items():
            for retained, volume in ((False, plain_volume), (True, retained_volume)):
                with self.subTest(family=family, retained=retained):
                    shape = self.parts[family, retained]
                    bounds = shape.bounding_box()
                    self.assertTrue(shape.is_valid)
                    self.assertEqual(len(shape.solids()), 1)
                    self.assertEqual(len(shape.shells()), 1)
                    self.assertAlmostEqual(bounds.size.X, length, delta=.001)
                    self.assertAlmostEqual(bounds.min.Z, 0, delta=.000001)
                    self.assertAlmostEqual(bounds.max.Z, 3.8, delta=.000001)
                    self.assertLess(abs(shape.volume - volume) / volume, .001)

    def test_twenty_tooth_mechanism_and_rib_stay_at_source_position(self):
        for family in ("M", "L"):
            dimensions = rail_dimensions(family)
            self.assertEqual(dimensions.valley_centers, D.valley_centers)
            self.assertEqual(dimensions.tooth_pitch, D.tooth_pitch)
            self.assertEqual(dimensions.retaining_start, D.retaining_start)
            self.assertEqual(dimensions.retaining_end, D.retaining_end)
            for retained in (False, True):
                shape = self.parts[family, retained]
                for x in (37.890, 41.8666, 81.9877, 89.9399, 114.0211):
                    with self.subTest(family=family, retained=retained, valley=x):
                        self.assertFalse(shape.is_inside((x, 2.01, 1.9)))
                        self.assertTrue(shape.is_inside((x, 1.88, 1.9)))
            self.assertTrue(self.parts[family, True].is_inside((20, -.7, 1.9)))
            self.assertFalse(self.parts[family, True].is_inside((125, -.7, 1.9)))

    def test_larger_sizes_add_full_width_shank_and_preserve_tapered_tip(self):
        for family in ("M", "L"):
            d = rail_dimensions(family)
            shape = self.parts[family, False]
            with self.subTest(family=family):
                self.assertTrue(shape.is_inside((125, 4.5, 1.9)))
                self.assertTrue(shape.is_inside((d.length - 8, 4.5, 1.9)))
                self.assertFalse(shape.is_inside((d.length - 4, 4.5, 1.9)))
                self.assertTrue(shape.is_inside((d.length - 4, 2.5, 1.9)))
                self.assertTrue(shape.is_inside((d.length - 2.0537, 1.3, 2.50)))
                self.assertFalse(shape.is_inside((d.length - 2.0537, 1.3, 2.60)))

    def test_family_names_and_invalid_sizes(self):
        self.assertIs(rail_dimensions("S"), D)
        for family in ("S", "M", "L"):
            spec = GearRailSpec(family)
            self.assertEqual(spec.slug, f"{family.lower()}_geared_rails")
            self.assertEqual(spec.name, f"{family} Geared Rails")
        for family in ("XL", "m", "unknown"):
            with self.subTest(family=family), self.assertRaises(ValueError):
                GearRailSpec(family)
        for changes in ({"extended_tail": True}, {"extended_tail": "yes"},
                        {"extended_tail": True, "tail_relief_radius": 5}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(D, **changes)


if __name__ == "__main__":
    unittest.main()
