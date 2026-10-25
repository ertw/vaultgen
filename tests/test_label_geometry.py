"""Physical invariants of the multicolor face-down label."""
import unittest

from build123d import Axis, Face, Solid

from vault.exports import precise_volume
from vault.label import build_label_parts, facade_transform, label_outline, to_facade, to_print
from vault.label_config import LabelConfiguration, label_dimensions


class LabelGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = LabelConfiguration(lines=[
            {'text':'B8 Øé','size':6,'color':'#ff0033'},
            {'text':'gyp 12','size':4,'color':'#ffffff'}])
        cls.parts, cls.check = build_label_parts(cls.config)

    def test_hollow_shell_keeps_counters_and_colors_connected_after_printing(self):
        body = self.parts['label_body']['shape']
        self.assertTrue(body.is_valid)
        self.assertEqual(len(body.solids()),1)
        self.assertEqual(len(body.shells()),1)
        self.assertAlmostEqual(self.check['counter_web_mm'],.3)
        self.assertAlmostEqual(self.check['color_volume_mm3'],self.check['shell_volume_mm3'],places=6)
        self.assertEqual(self.check['color_overlap_mm3'],0.)
        # Cavity opens at the rear; the continuous face web remains above it.
        self.assertFalse(body.is_inside((23.5,9.7,.5)))
        self.assertTrue(body.is_inside((23.5,9.7,1.25)))
        for item in self.parts.values():
            self.assertTrue(item['shape'].is_valid)
            self.assertEqual(len(item['shape'].shells()),len(item['shape'].solids()))

    def test_print_transform_is_common_and_places_inlays_on_the_bed(self):
        self.assertEqual(len(self.parts),3)
        for name,item in self.parts.items():
            native = item['shape'].bounding_box()
            printed = to_print(item['shape']).bounding_box()
            self.assertAlmostEqual(printed.min.X,47-native.max.X,places=5)
            self.assertAlmostEqual(printed.min.Y,native.min.Y,places=5)
            self.assertAlmostEqual(printed.min.Z,0.,places=5)
            self.assertAlmostEqual(printed.max.Z,2 if name=='label_body' else .6,places=5)
            self.assertAlmostEqual(precise_volume(to_print(item['shape'])),precise_volume(item['shape']),places=6)
        # Inlays keep their position, not an individually recentered origin.
        self.assertGreater(to_print(self.parts['label_ink_1']['shape']).bounding_box().min.X,3)

    def test_solid_back_changes_only_the_cavity(self):
        solid,_ = build_label_parts(LabelConfiguration(lines=self.config.lines,hollow=False))
        self.assertTrue(solid['label_body']['shape'].is_inside((23.5,9.7,.5)))
        for name in ('label_ink_1','label_ink_2'):
            self.assertAlmostEqual(precise_volume(solid[name]['shape']),precise_volume(self.parts[name]['shape']),places=7)
        cavity = Solid.extrude(Face(label_outline(.8)),(0,0,1.1))
        self.assertAlmostEqual(precise_volume(solid['label_body']['shape'])-
                               precise_volume(self.parts['label_body']['shape']),precise_volume(cavity),places=6)

    def test_facade_rotation_keeps_text_upright_and_normal_outward(self):
        from build123d import Vertex
        origin = to_facade(Vertex(0,0,0)).center()
        up = to_facade(Vertex(0,1,0)).center()-origin
        normal = to_facade(Vertex(0,0,1)).center()-origin
        for actual,expected in zip(up,(0,0,1)):
            self.assertAlmostEqual(actual,expected,places=9)
        for actual,expected in zip(normal,(0,1,0)):
            self.assertAlmostEqual(actual,expected,places=9)

    def test_font_overhangs_union_into_one_material_without_double_counting(self):
        for text in ('YY','YÝ','íì'):
            with self.subTest(text=text):
                parts,check = build_label_parts(LabelConfiguration(lines=[
                    {'text':text,'size':6,'color':'#ffffff'}]))
                self.assertTrue(check['passed'])
                self.assertAlmostEqual(check['shell_volume_mm3'],check['color_volume_mm3'],places=6)
                ink = parts['label_ink_1']['shape']
                self.assertTrue(ink.is_valid)
                solids = list(ink.solids())
                for i,first in enumerate(solids):
                    for second in solids[i+1:]:
                        common = first.intersect(second)
                        overlap = sum(abs(precise_volume(s)) for s in common) if common else 0.
                        self.assertAlmostEqual(overlap,0.,places=7)

    def test_wider_labels_extend_the_straight_section_without_scaling_text_or_profiles(self):
        for family,width in (('M',91.6),('L',129.4)):
            with self.subTest(family=family):
                config = LabelConfiguration(family=family,lines=self.config.lines)
                parts,check = build_label_parts(config)
                body = parts['label_body']['shape']
                self.assertAlmostEqual(body.bounding_box().size.X,width,places=5)
                self.assertAlmostEqual(body.bounding_box().size.Y,19.4,places=5)
                self.assertAlmostEqual(body.bounding_box().size.Z,2.,places=5)
                # Added length is just the unchanged .9 mm face and two .8 mm
                # rims around the 1.1 mm deep cavity, not scaled rounded ends.
                self.assertAlmostEqual(check['shell_volume_mm3']-self.check['shell_volume_mm3'],
                                       (width-47)*(.9*19.4+2*.8*1.1),places=5)
                self.assertFalse(body.is_inside((width/2,9.7,.5)))
                self.assertTrue(body.is_inside((width/2,9.7,1.25)))
                for name in ('label_ink_1','label_ink_2'):
                    ink = parts[name]['shape']
                    original = self.parts[name]['shape']
                    self.assertAlmostEqual(precise_volume(ink),precise_volume(original),places=6)
                    self.assertAlmostEqual(ink.bounding_box().min.X-original.bounding_box().min.X,
                                           (width-47)/2,places=5)
                printed = to_print(body,config).bounding_box()
                self.assertAlmostEqual(printed.min.X,0.,places=5)
                self.assertAlmostEqual(printed.max.X,width,places=5)
                self.assertAlmostEqual(printed.min.Z,0.,places=5)
                placed = to_facade(body,config).bounding_box()
                self.assertAlmostEqual(placed.min.X,32.3,places=5)
                self.assertAlmostEqual(placed.max.X,32.3+width,places=5)
                self.assertEqual(check['print_transform'][12],width)
                self.assertEqual(check['facade_transform'],facade_transform(family))
                self.assertEqual(check['label_dimensions'],label_dimensions(family))


if __name__ == '__main__':
    unittest.main()
