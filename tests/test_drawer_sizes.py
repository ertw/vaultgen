"""Size changes retain fixed mating dimensions and align paired drawer parts."""
import unittest

from vault.box import BoxSpec, build_box
from vault.build import select_spec
from vault.drawer import DrawerLayout
from vault.facade import FacadeSpec, build_facade
from vault.spec import ModuleSpec


class DrawerSizeTests(unittest.TestCase):
    def test_part_names_validation_and_shared_attachment_axes(self):
        self.assertEqual(BoxSpec('L', 7, 2).slug, 'l7_box_2f')
        self.assertEqual(BoxSpec('M', 3, 1).name, 'M3 Box 1F')
        self.assertEqual(FacadeSpec('M', 2).slug, 'm2f_facade')
        self.assertEqual(FacadeSpec('L', 1).name, 'L1F Facade')
        self.assertEqual(BoxSpec('S', 4, 4).slug, 's4_box_4f')
        self.assertEqual(FacadeSpec('M', 4).slug, 'm4f_facade')
        for family, outer in [('S', 51.45), ('M', 92.45), ('L', 130.25)]:
            layout = DrawerLayout(ModuleSpec(family, 7, 4))
            self.assertIn((-outer, 71.5), layout.screw_positions)
            self.assertIn((-outer, 119.5), layout.screw_positions)
            self.assertIn((outer, 167.5), layout.screw_positions)
            self.assertIn((outer, 23.5), layout.screw_positions)
            self.assertIn((51.45, 23.5), layout.screw_positions)
            self.assertEqual(len(layout.screw_positions), 8 if family == 'S' else 10)
        for constructor, arguments in [(BoxSpec, ('XL', 4, 1)),
                                       (BoxSpec, ('S', 4, 3)),
                                       (BoxSpec, ('S', 2, 1)),
                                       (FacadeSpec, ('XL', 1)),
                                       (FacadeSpec, ('M', 5))]:
            with self.assertRaises(ValueError):
                constructor(*arguments)

    def test_four_floor_part_selection_retains_shared_runner_geometry(self):
        for part in ('runner_guides', 'runner_slides'):
            for family in ('S', 'M', 'L'):
                self.assertEqual(select_spec(part, family, 7, 4), select_spec(part, family, 7, 1))
                with self.assertRaises(ValueError):
                    select_spec(part, family, 7, 3)
        self.assertEqual(select_spec('box', 'L', 7, 4, drawer_columns=2), BoxSpec('S', 7, 4))
        self.assertEqual(select_spec('facade', 'L', 7, 4, drawer_columns=2), FacadeSpec('S', 4))

    def test_generated_drawer_extremes(self):
        # Include each family, shortest/longest supported catalog depths and
        # all heights. Probes test wall thickness and moving mating datums,
        # rather than merely repeating constructor arithmetic.
        for spec in (ModuleSpec('S', 3, 2), ModuleSpec('M', 5, 1), ModuleSpec('L', 7, 2),
                     ModuleSpec('S', 3, 4), ModuleSpec('M', 5, 4), ModuleSpec('L', 7, 4)):
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
                # The lower bridge relief moves with depth and the open
                # side's width, retaining the same crown and blind stop.
                center_y = spec.depth-3.1
                for x, roof in ((-65-layout.width_delta, 11.807), (60, 11.89)):
                    self.assertFalse(box.is_inside((x, center_y, roof+1.5)))
                    self.assertTrue(box.is_inside((x, center_y, roof+1.54)))
                    for offset in (-1.1, 1.1):
                        self.assertFalse(box.is_inside((x, center_y+offset, roof+1.2)))
                        self.assertTrue(box.is_inside((x, center_y+offset, roof+1.4)))
                    for offset in (-1.7, 1.7):
                        self.assertTrue(box.is_inside((x, center_y+offset, roof+.2)))
                self.assertFalse(box.is_inside((66.29, center_y, 13)))
                self.assertTrue(box.is_inside((66.31, center_y, 13)))
                self.assertFalse(facade.is_inside((0,5,23.5)))
                # The shared silhouette rebate follows the taller/wider size.
                for z in (.5, spec.height-.5):
                    self.assertFalse(facade.is_inside((0,.25,z)))
                    self.assertTrue(facade.is_inside((0,.75,z)))


if __name__ == '__main__':
    unittest.main()
