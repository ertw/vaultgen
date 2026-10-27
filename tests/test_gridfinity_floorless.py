"""Open Gridfinity cell bottoms retain supporting webs and bin seating."""
from dataclasses import replace
from itertools import product
import unittest

from vault.box import BoxSpec, build_box
from vault.gridfinity import GridfinityLayout
from tools.check_gridfinity import audit_gridfinity


class FloorlessGridfinityLayoutTests(unittest.TestCase):
    def test_floorless_layout_retains_thin_floor_socket_datums_for_every_size(self):
        for family, depth, height in product(('S', 'M', 'L'), range(3, 8), (1, 2)):
            spec = BoxSpec(family, depth, height, 0, 'gridfinity')
            with self.subTest(spec=spec):
                open_grid = GridfinityLayout(spec)
                closed_grid = GridfinityLayout(replace(spec, box_floor=.8))
                self.assertEqual(open_grid.centers, closed_grid.centers)
                self.assertEqual(open_grid.floor_z, 5.8)
                self.assertEqual(open_grid.socket_height, 5.0)
                self.assertEqual(open_grid.notes()['closed_floor_mm'], 0)
                self.assertAlmostEqual(open_grid.notes()['foundation_thickness_mm'], .8)


class FloorlessGridfinityGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = []
        # Short grids cover all widths, both heights and every rear style
        # without making the whole depth/height matrix build native solids.
        for spec in (BoxSpec('S', 3, 1, 0, 'gridfinity'),
                     BoxSpec('M', 3, 1, 0, 'gridfinity', 'waffle'),
                     BoxSpec('L', 3, 2, 0, 'gridfinity', 'miura')):
            plain = build_box(spec=replace(spec, box_floor=.8, box_variant='plain'))
            grid = build_box(spec=spec)
            report = audit_gridfinity(plain, grid, spec)
            cls.cases.append((spec, grid, report))

    def test_open_cells_remove_only_their_floors_and_accept_supported_bins(self):
        for spec, grid, report in self.cases:
            with self.subTest(spec=spec):
                self.assertTrue(report['passed'], report)
                self.assertTrue(report['open_cell_floor_checks'])
                self.assertLess(report['removal_outside_cell_openings_mm3'], 1e-5)
                self.assertLess(report['material_remaining_in_cell_openings_mm3'], 1e-5)
                self.assertGreater(report['lowered_single_bin_collision_mm3'], .1)
                self.assertGreater(report['lowered_full_grid_bin_collision_mm3'], .1)
                self.assertIn('Floorless', grid.label)

    def test_web_foundations_and_outer_strips_connect_grid_to_tray_walls(self):
        for spec, grid, _ in self.cases:
            layout = GridfinityLayout(spec)
            with self.subTest(spec=spec):
                # Between adjacent columns/rows, the narrow web remains both
                # below the socket datum and partway up the mating profile.
                x0, y0 = layout.centers[0]
                for column in range(1, layout.columns):
                    for row in range(layout.rows):
                        for z in (5.4, 8.0):
                            self.assertTrue(grid.is_inside((
                                layout.x_min+column*42, y0+row*42, z)))
                for row in range(1, layout.rows):
                    for column in range(layout.columns):
                        for z in (5.4, 8.0):
                            self.assertTrue(grid.is_inside((
                                x0+column*42, layout.y_min+row*42, z)))
                # Traverse each foundation strip from the outer grid into
                # the retained floor outside it, on all four sides.
                for offset in (-.2, 0, .2):
                    for x in (layout.x_min+offset, layout.x_max+offset):
                        self.assertTrue(grid.is_inside((x, y0, 5.4)))
                    for y in (layout.y_min+offset, layout.y_max+offset):
                        self.assertTrue(grid.is_inside((x0, y, 5.4)))


if __name__ == '__main__':
    unittest.main()
