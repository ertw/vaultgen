"""Native rear-wall thinning preserves mechanical lands and minimum thickness."""
from dataclasses import replace
import unittest

from vault.box import BoxSpec, build_box
from vault.box_wall_patterns import apply_box_rear_pattern, rear_pattern_panel
from tools.check_box_wall_patterns import allowed_rear_volume, audit_box_rear_pattern


class BoxRearPatternGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = BoxSpec('S', 3, 1)
        cls.plain = build_box(spec=cls.spec)
        cls.reports = {}
        for style in ('waffle', 'miura'):
            spec = replace(cls.spec, box_rear_pattern=style)
            # Exercise the public box constructor for one option as well as
            # the standalone shared-pattern application for the other.
            shape = build_box(spec=spec) if style == 'miura' else apply_box_rear_pattern(cls.plain, spec)
            cls.reports[style] = audit_box_rear_pattern(cls.plain, shape, spec)

    def test_both_styles_preserve_interfaces_and_have_two_line_facets(self):
        for style, report in self.reports.items():
            with self.subTest(style=style):
                self.assertTrue(report['passed'], report)
                self.assertAlmostEqual(report['minimum_web_mm'], 1.3, delta=.01)
                self.assertGreater(report['removed_volume_mm3'], 100)
                self.assertTrue(all(item['passed'] for item in report['protected_features']))

    def test_styles_are_distinct(self):
        self.assertNotAlmostEqual(self.reports['waffle']['removed_volume_mm3'],
                                  self.reports['miura']['removed_volume_mm3'], places=2)

    def test_plain_does_not_rebuild_or_modify_geometry(self):
        self.assertIs(apply_box_rear_pattern(self.plain, self.spec), self.plain)

    def test_tall_gridfinity_box_keeps_original_base_and_thicker_floor(self):
        spec = BoxSpec('M', 3, 2, box_floor=3., box_variant='gridfinity',
                       box_rear_pattern='miura')
        plain = build_box(spec=replace(spec, box_rear_pattern='plain'))
        patterned = apply_box_rear_pattern(plain, spec)
        report = audit_box_rear_pattern(plain, patterned, spec)
        self.assertTrue(report['passed'], report)
        base = next(item for item in report['protected_features'] if item['feature'] == 'gridfinity_base')
        self.assertLessEqual(base['removed_mm3'], 1e-5)


class BoxRearPatternPlacementTests(unittest.TestCase):
    def test_floorless_gridfinity_preserves_rear_rim_and_fillet_lands(self):
        for family in ('S', 'M', 'L'):
            for height in (1, 2):
                with self.subTest(family=family, height=height):
                    solid = BoxSpec(family, 3, height, box_variant='gridfinity')
                    floorless = replace(solid, box_floor=0.)
                    self.assertEqual(rear_pattern_panel(solid), rear_pattern_panel(floorless))
                    before = allowed_rear_volume(solid).bounding_box()
                    after = allowed_rear_volume(floorless).bounding_box()
                    self.assertEqual(tuple(before.min), tuple(after.min))
                    self.assertEqual(tuple(before.max), tuple(after.max))

    def test_all_supported_drawer_panels_clear_corners_and_floor(self):
        for family, width in (('S', 114.2), ('M', 203.4), ('L', 279.0)):
            for height in (1, 2):
                for floor in (.8, 3.):
                    with self.subTest(family=family, height=height, floor=floor):
                        spec = BoxSpec(family, 7, height, box_floor=floor)
                        panel = rear_pattern_panel(spec)
                        x0, z0, x1, z1 = panel.bounds
                        self.assertAlmostEqual(x1-x0, width)
                        self.assertAlmostEqual(z0, 9+floor)
                        self.assertAlmostEqual(z1, 39.5+48*(height-1))
                        self.assertEqual(panel.point(0, z0, 0), (0, 2.3, z0))
                        self.assertEqual(panel.point(0, z0, 3), (0, 5.3, z0))


if __name__ == '__main__':
    unittest.main()
