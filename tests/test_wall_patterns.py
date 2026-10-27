"""Native containment, minimum web, and working interfaces of module reliefs."""
from dataclasses import replace
import unittest

from vault.connectors import ConnectorParameters
from vault.model import build_module
from vault.shell import ShellDimensions
from vault.spec import ModuleSpec
from vault.wall_patterns import apply_wall_pattern, pattern_cutters, pattern_panels, _waffle_cutters
from tools.check_wall_patterns import audit_pattern


class PatternGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plain = build_module(ModuleSpec('S', 3, 1))
        cls.reports = {}
        for construction in ('recessed', 'corrugated'):
            for pattern in ('waffle', 'miura'):
                spec = ModuleSpec('S', 3, 1, wall_pattern=pattern, pattern_construction=construction)
                shape = apply_wall_pattern(cls.plain, spec, ShellDimensions(), ConnectorParameters())
                cls.reports[construction, pattern] = audit_pattern(cls.plain, shape, spec)

    def test_both_patterns_preserve_native_interfaces_and_minimum_web(self):
        for (construction, pattern), report in self.reports.items():
            with self.subTest(construction=construction, pattern=pattern):
                self.assertTrue(report['passed'], report)
                self.assertAlmostEqual(report['minimum_web_mm'], 1.3, delta=.01)

    def test_both_patterns_remove_measurable_material(self):
        for (construction, pattern), report in self.reports.items():
            with self.subTest(construction=construction, pattern=pattern):
                self.assertGreater(report['removed_volume_mm3'], 100)
        for construction in ('recessed', 'corrugated'):
            self.assertNotAlmostEqual(self.reports[construction, 'waffle']['removed_volume_mm3'],
                                      self.reports[construction, 'miura']['removed_volume_mm3'], places=2)
        for pattern in ('waffle', 'miura'):
            self.assertGreater(self.reports['corrugated', pattern]['removed_volume_mm3'],
                               self.reports['recessed', pattern]['removed_volume_mm3'])


class PatternParameterGeometryTests(unittest.TestCase):
    def test_large_pitch_still_reaches_every_requested_face(self):
        spec = ModuleSpec('S', 3, 1, wall_pattern='waffle', pattern_pitch=40)
        panels = pattern_panels(spec, ShellDimensions(), ConnectorParameters())
        self.assertEqual({panel.face for panel in panels}, {'left', 'right', 'top', 'bottom'})
        for panel in panels:
            with self.subTest(face=panel.face):
                cutters = list(_waffle_cutters(panel, spec))
                self.assertTrue(cutters)
                self.assertTrue(all(cutter.is_valid and cutter.volume > 0 for cutter in cutters))

    def test_custom_native_skin_must_retain_two_lines(self):
        for changes in ({'skin': 2.9}, {'channel_outer_inset': 2.9}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'two extrusion lines'):
                pattern_cutters(ModuleSpec(wall_pattern='waffle'),
                                replace(ShellDimensions(), **changes), ConnectorParameters())

    def test_sides_only_does_not_depend_on_top_skin(self):
        cutters = pattern_cutters(ModuleSpec(wall_pattern='waffle', pattern_faces='sides'),
                                  replace(ShellDimensions(), skin=2.0), ConnectorParameters())
        self.assertTrue(cutters)
        self.assertTrue(all(cutter.is_valid for cutter in cutters))

    def test_tall_wide_module_keeps_divider_and_repeats_side_panels(self):
        spec = ModuleSpec('L', 7, 2, drawer_columns=2, wall_pattern='miura')
        d = ShellDimensions()
        panels = pattern_panels(spec, d, ConnectorParameters())
        self.assertEqual(len([panel for panel in panels if panel.face == 'left']), 2)
        self.assertEqual(len([panel for panel in panels if panel.face == 'right']), 2)
        for panel in panels:
            u0, v0, u1, v1 = panel.bounds
            self.assertGreater(v0, d.rear_notch_depth)
            self.assertLess(v1, spec.depth-d.pocket_front_offset-d.pocket_length)
            if panel.face in ('top', 'bottom'):
                self.assertTrue(any(a < -d.side_wall and c > d.side_wall and b < v0 and e > v1
                                    for a, b, c, e in panel.keepouts))
            else:
                self.assertFalse(u0 <= 47.5 <= u1)

    def test_custom_bore_positions_keep_their_skin_footprints(self):
        spec = ModuleSpec(wall_pattern='waffle')
        d = replace(ShellDimensions(), bore_inset=35, bore_lower_z=3,
                    bore_upper_z=44, bore_entry_radius=3.5)
        x = spec.half_width-d.bore_inset
        for panel in pattern_panels(spec, d, ConnectorParameters()):
            if panel.face in ('top', 'bottom'):
                for side in (-1, 1):
                    self.assertTrue(any(a < side*x-d.bore_entry_radius and c > side*x+d.bore_entry_radius
                                        and b <= 0 and e >= d.bore_depth
                                        for a, b, c, e in panel.keepouts))


if __name__ == '__main__':
    unittest.main()
