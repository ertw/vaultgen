"""Native socket mating, floor retention, and unchanged drawer interfaces."""
from dataclasses import replace
from itertools import product
import unittest

from vault.box import BoxSpec, build_box
from vault.drawer import DrawerLayout
from vault.gridfinity import GridfinityLayout, socket_cutter
from tools.check_gridfinity import audit_gridfinity


class GridfinityLayoutTests(unittest.TestCase):
    def test_whole_cells_fit_all_generator_sizes_and_floors(self):
        for family, depth, height, floor in product(('S', 'M', 'L'), range(3, 8), (1, 2), (.8, 3.0)):
            spec = BoxSpec(family, depth, height, floor, 'gridfinity')
            grid, drawer = GridfinityLayout(spec), DrawerLayout(spec)
            with self.subTest(spec=spec):
                self.assertEqual(grid.columns, {'S': 3, 'M': 5, 'L': 6}[family])
                self.assertEqual(grid.rows, depth)
                self.assertEqual(len(grid.centers), grid.columns*depth)
                self.assertLess(grid.x_max, 63.6+drawer.width_delta)
                self.assertGreater(grid.y_min, 6.3)
                self.assertLess(grid.y_max, 177.1+drawer.depth_delta)
                self.assertAlmostEqual(grid.floor_z, 5+floor)
                self.assertEqual(grid.socket_height, 5.0)

    def test_plain_identity_is_preserved_and_variants_are_distinct(self):
        self.assertEqual(BoxSpec().slug, 's4_box_1f')
        self.assertEqual(BoxSpec(box_floor=3).slug, 's4_box_1f_floor_3mm')
        self.assertEqual(BoxSpec(box_variant='gridfinity').slug, 's4_box_1f_gridfinity')
        self.assertEqual(BoxSpec(box_floor=3, box_variant='gridfinity').slug,
                         's4_box_1f_floor_3mm_gridfinity')
        for variant in (None, '', 'GRIDFINITY', [], True):
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                BoxSpec(box_variant=variant)


class GridfinityGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for spec in (BoxSpec('S', 3, 1, .8, 'gridfinity'),
                     BoxSpec('S', 4, 1, 3, 'gridfinity'),
                     BoxSpec('L', 7, 2, 3, 'gridfinity')):
            plain = build_box(spec=replace(spec, box_variant='plain'))
            grid = build_box(spec=spec)
            cls.cases.append((spec, plain, grid, audit_gridfinity(plain, grid, spec)))

    def test_native_representative_drawers_retain_interfaces_and_accept_bins(self):
        for spec, plain, grid, report in self.cases:
            with self.subTest(spec=spec):
                self.assertTrue(report['passed'], report)
                self.assertGreater(report['added_volume_mm3'], 1000)
                self.assertIn('Gridfinity', grid.label)

    def test_nominal_socket_has_straight_and_chamfered_sections(self):
        cutter = socket_cutter()
        # Independent section expectations include the relieved bottom and
        # both 45-degree transitions; test straight sides and rounded corners.
        for z, width, radius in ((.175, 36.3, 1.15), (.7, 37, 1.5),
                                  (1.7, 37.7, 1.85), (3.9, 39.8, 2.9)):
            with self.subTest(z=z):
                half = width/2
                self.assertTrue(cutter.is_inside((half-.01, 0, z)))
                self.assertFalse(cutter.is_inside((half+.01, 0, z)))
                diagonal = half-radius+radius/(2**.5)
                self.assertTrue(cutter.is_inside((diagonal-.01, diagonal-.01, z)))
                self.assertFalse(cutter.is_inside((diagonal+.01, diagonal+.01, z)))


if __name__ == '__main__':
    unittest.main()
