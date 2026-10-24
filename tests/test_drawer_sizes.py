"""Size changes retain fixed mating dimensions and align paired drawer parts."""
import unittest

from vault.box import BoxSpec, build_box
from vault.drawer import DrawerLayout
from vault.facade import FacadeSpec, build_facade
from vault.spec import ModuleSpec


class DrawerSizeTests(unittest.TestCase):
    def test_part_names_validation_and_shared_attachment_axes(self):
        self.assertEqual(BoxSpec('L', 7, 2).slug, 'l7_box_2f')
        self.assertEqual(BoxSpec('M', 3, 1).name, 'M3 Box 1F')
        self.assertEqual(FacadeSpec('M', 2).slug, 'm2f_facade')
        self.assertEqual(FacadeSpec('L', 1).name, 'L1F Facade')
        for family, outer in [('S', 51.45), ('M', 92.45), ('L', 130.25)]:
            layout = DrawerLayout(ModuleSpec(family, 7, 2))
            self.assertIn((-outer, 71.5), layout.screw_positions)
            self.assertIn((outer, 23.5), layout.screw_positions)
            self.assertIn((51.45, 23.5), layout.screw_positions)
        for constructor, arguments in [(BoxSpec, ('XL', 4, 1)),
                                       (BoxSpec, ('S', 4, 4)),
                                       (BoxSpec, ('S', 2, 1)),
                                       (FacadeSpec, ('XL', 1)),
                                       (FacadeSpec, ('M', 4))]:
            with self.assertRaises(ValueError):
                constructor(*arguments)

    def test_generated_drawer_extremes(self):
        # Include each family, shortest/longest supported catalog depths and
        # both heights. Probes test wall thickness and moving mating datums,
        # rather than merely repeating constructor arithmetic.
        for spec in (ModuleSpec('S', 3, 2), ModuleSpec('M', 5, 1), ModuleSpec('L', 7, 2)):
            with self.subTest(spec=spec):
                layout = DrawerLayout(spec)
                box = build_box(spec=BoxSpec(spec.family, spec.depth_units, spec.height_units))
                facade = build_facade(spec=FacadeSpec(spec.family, spec.height_units))
                for part in (box, facade):
                    self.assertTrue(part.is_valid)
                    self.assertEqual(len(part.solids()), 1)
                    self.assertEqual(len(part.shells()), 1)
                for actual, expected in zip(box.bounding_box().size,
                                             (spec.width-30.6, spec.depth-2.3, spec.height-9.5)):
                    self.assertAlmostEqual(actual, expected, places=5)
                for actual, expected in zip(facade.bounding_box().size, (spec.width, 10, spec.height)):
                    # The rolled silhouette loses ~0.021 mm at its widest
                    # section when the 0.5 mm seating rebate is cut.
                    self.assertAlmostEqual(actual, expected, delta=.03)
                self.assertAlmostEqual(box.bounding_box().max.Y, spec.depth, places=5)
                self.assertTrue(box.is_inside((0, 50, 5.79)))
                self.assertFalse(box.is_inside((0, 50, 5.81)))
                for x,z in layout.screw_positions:
                    self.assertFalse(box.is_inside((x, spec.depth-5, z)))
                    self.assertTrue(box.is_inside((x+3, spec.depth-5, z)))
                    self.assertFalse(facade.is_inside((x, 3, z)))
                    self.assertTrue(facade.is_inside((x+3, 3, z)))
                for tier in spec.tier_offsets:
                    for side in (-1, 1):
                        self.assertFalse(box.is_inside((side*(65.4+layout.width_delta),50,23.5+tier)))
                        self.assertTrue(box.is_inside((side*(64.8+layout.width_delta),50,23.5+tier)))
                for side,z in ((-1,8), (1,39)):
                    self.assertFalse(box.is_inside((side*(67+layout.width_delta),spec.depth-3,z)))
                self.assertFalse(facade.is_inside((0,5,23.5)))
                # The shared silhouette rebate follows the taller/wider size.
                for z in (.5, spec.height-.5):
                    self.assertFalse(facade.is_inside((0,.25,z)))
                    self.assertTrue(facade.is_inside((0,.75,z)))


if __name__ == '__main__':
    unittest.main()
