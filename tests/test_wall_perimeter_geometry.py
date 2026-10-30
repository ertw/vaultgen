"""Shared wall targets preserve native lands and runner datums."""
from dataclasses import replace
import unittest

from vault.box import BoxSpec, build_box
from vault.connectors import ConnectorParameters
from vault.model import build_module
from vault.shell import ShellDimensions
from vault.spec import ModuleSpec, wall_target_thickness
from vault.wall_patterns import apply_wall_pattern
from tools.check_wall_patterns import audit_pattern
from tools.check_box_wall_patterns import audit_box_rear_pattern


class WallPerimeterSpecificationTests(unittest.TestCase):
    def test_nozzle_and_perimeter_targets_have_distinct_stable_identities(self):
        for constructor in (ModuleSpec, BoxSpec):
            variants = []
            for pattern in ('plain', 'miura'):
                for count in (1, 2):
                    for nozzle, line in ((.6, .65), (.8, .85)):
                        spec = constructor(wall_pattern=pattern, wall_perimeters=count, nozzle_size=nozzle)
                        self.assertAlmostEqual(wall_target_thickness(spec), count*line)
                        variants.append(spec.slug)
                        self.assertEqual(spec.slug, replace(spec).slug)
            self.assertEqual(len(set(variants)), 8)
            self.assertNotIn(constructor().slug, variants)

    def test_full_width_uses_plain_and_canonical_inactive_settings(self):
        for constructor in (ModuleSpec, BoxSpec):
            full = constructor(wall_perimeters='full')
            self.assertEqual(full, constructor(wall_perimeters='full', wall_pattern='miura',
                                              nozzle_size=.8, pattern_pitch=20, pattern_depth=.8))
            self.assertIsNone(wall_target_thickness(full))
            self.assertEqual(full.wall_pattern, 'plain')

    def test_invalid_targets_cannot_reach_native_geometry(self):
        for constructor in (ModuleSpec, BoxSpec):
            for count in (True, False, 0, 3, 1., '2', [], {}):
                with self.subTest(constructor=constructor.__name__, count=count), self.assertRaises(ValueError):
                    constructor(wall_perimeters=count)
            for nozzle in (True, '0.6', .4, .7, float('nan'), float('inf')):
                with self.subTest(constructor=constructor.__name__, nozzle=nozzle), self.assertRaises(ValueError):
                    constructor(wall_perimeters=2, nozzle_size=nozzle)
            with self.assertRaises(ValueError):
                constructor(wall_perimeters=2, wall_pattern='waffle')

    def test_new_module_controls_always_use_all_panels_and_paired_relief(self):
        spec = ModuleSpec(wall_pattern='miura', wall_perimeters=2, nozzle_size=.8,
                          pattern_faces='sides', pattern_construction='recessed', pattern_line_width=.65)
        self.assertEqual(spec.pattern_faces, 'all')
        self.assertEqual(spec.pattern_construction, 'corrugated')
        self.assertEqual(spec.pattern_line_width, .85)


class WallPerimeterGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = build_module(ModuleSpec('S', 3, 1))
        cls.box = build_box(spec=BoxSpec('S', 3, 1))

    def test_plain_and_miura_minimum_and_maximum_targets(self):
        for pattern, count, nozzle in (('plain', 1, .6), ('plain', 2, .8),
                                      ('miura', 1, .6), ('miura', 2, .8)):
            with self.subTest(pattern=pattern, count=count, nozzle=nozzle):
                module_spec = ModuleSpec('S', 3, 1, wall_pattern=pattern,
                                         wall_perimeters=count, nozzle_size=nozzle)
                module = apply_wall_pattern(self.module, module_spec, ShellDimensions(), ConnectorParameters())
                module_report = audit_pattern(self.module, module, module_spec)
                self.assertTrue(module_report['passed'], module_report)
                self.assertAlmostEqual(module_report['minimum_web_mm'], wall_target_thickness(module_spec), delta=.02)
                box_spec = BoxSpec('S', 3, 1, wall_pattern=pattern,
                                   wall_perimeters=count, nozzle_size=nozzle)
                box = build_box(spec=box_spec)
                box_report = audit_box_rear_pattern(self.box, box, box_spec)
                self.assertTrue(box_report['passed'], box_report)
                self.assertAlmostEqual(box_report['minimum_web_mm'], wall_target_thickness(box_spec), delta=.02)
                # Registered runner side remains X=64.9; only its cavity side moves.
                thickness = wall_target_thickness(box_spec)
                for sign in (-1, 1):
                    self.assertTrue(box.is_inside((sign*(64.9-thickness+.02), 70, 23.5)))
                    self.assertFalse(box.is_inside((sign*(64.9-thickness-.02), 70, 23.5)))
                    self.assertFalse(box.is_inside((sign*(64.9+.02), 70, 23.5)))

    def test_full_width_module_keeps_original_geometry(self):
        full = ModuleSpec('S', 3, 1, wall_perimeters='full')
        self.assertIs(apply_wall_pattern(self.module, full, ShellDimensions(), ConnectorParameters()), self.module)


if __name__ == '__main__':
    unittest.main()
