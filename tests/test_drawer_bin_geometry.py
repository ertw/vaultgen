"""Plain-drawer registration, thin anisotropic Miura joins and footless floors."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from build123d import Plane, Solid

from vault.bin import build_bins
from vault.bin_config import BinConfiguration
from vault.tessellation import export_print_mesh
from tools.check_drawer_bins import (audit_drawer_bins, junction_layer_samples,
                                     normal_wall_samples)
from tools.check_gridfinity_bins import intersection_volume


class DrawerBinGeometryTests(unittest.TestCase):
    def test_full_s4_miura_one_perimeter_print_mesh_closes_corner_seams(self):
        # The reported layout passed native-solid checks but had micron-sized
        # endpoint slivers that collapsed when written as float32 STL vertices.
        dividers = tuple({'axis':'x','x':x,'y':y} for x in (1,2) for y in (2,3))
        dividers += tuple({'axis':'y','x':x,'y':2} for x in range(3))
        config = BinConfiguration(container_type='drawer', depth_units=4,
            wall_pattern='miura', wall_perimeters=1, dividers=dividers)
        part = build_bins(config)['bin_01']
        self.assertTrue(part.is_valid)
        self.assertEqual((len(part.solids()), len(part.shells())), (1,1))
        bounds = part.bounding_box()
        printable = part.translate((-bounds.min.X, -bounds.min.Y, -bounds.min.Z))
        with TemporaryDirectory() as directory:
            mesh = export_print_mesh(printable, Path(directory)/'drawer.stl')
            self.assertTrue(mesh.is_watertight)
            self.assertTrue(mesh.is_winding_consistent)
            self.assertGreater(mesh.volume, 0.)

    def test_thick_floor_single_cell_miura_two_perimeter_rim_retains_normal_thickness(self):
        # The shorter 1F cavity above a 3 mm drawer floor previously failed
        # every allowed offset refinement with a half-row outer rim fade.
        config = BinConfiguration(container_type='drawer', depth_units=3,
            drawer_floor=3., cells=((0,0),), wall_pattern='miura', wall_perimeters=2)
        part = build_bins(config)['bin_01']
        self.assertTrue(part.is_valid)
        self.assertEqual((len(part.solids()), len(part.shells())), (1,1))
        self.assertAlmostEqual(part.bounding_box().max.Z, config.height_mm, places=6)
        samples = normal_wall_samples(part, config)
        self.assertGreaterEqual(len(samples), 8)
        self.assertTrue(all(sample['passed'] for sample in samples), samples)

    def test_anisotropic_miura_t_and_cross_joins_and_free_ends_in_both_wall_sizes(self):
        # One X junction, one T junction and two free ends, on unequal X/Y
        # pitches. This catches 42 mm registration left in the shared builder.
        dividers = ({'axis':'x','x':1,'y':0}, {'axis':'x','x':1,'y':1},
                    {'axis':'x','x':2,'y':1},
                    {'axis':'y','x':0,'y':1}, {'axis':'y','x':1,'y':1},
                    {'axis':'y','x':2,'y':1})
        for perimeters in (1, 2):
            with self.subTest(perimeters=perimeters):
                config = BinConfiguration(container_type='drawer', depth_units=3,
                    wall_pattern='miura', wall_perimeters=perimeters, dividers=dividers)
                self.assertNotAlmostEqual(config.pitch_x_mm, config.pitch_y_mm)
                part = build_bins(config)['bin_01']
                self.assertTrue(part.is_valid)
                self.assertEqual((len(part.solids()), len(part.shells())), (1,1))
                samples = normal_wall_samples(part, config)
                self.assertGreaterEqual(len(samples), 12)
                self.assertTrue(all(sample['passed'] for sample in samples), samples)
                layers = junction_layer_samples(part, config, config.components[0])
                vertices = {tuple(sample['junction_mm']) for sample in layers}
                self.assertIn((config.pitch_x_mm, config.pitch_y_mm), vertices)
                self.assertIn((2*config.pitch_x_mm, config.pitch_y_mm), vertices)
                self.assertNotIn((config.pitch_x_mm, 2*config.pitch_y_mm), vertices)
                self.assertNotIn((2*config.pitch_x_mm, 2*config.pitch_y_mm), vertices)
                self.assertTrue(all(sample['passed'] for sample in layers), layers)
                if perimeters == 1:
                    # Deliberately detach a short arm above the floor. Whole
                    # solid validity alone still passes; layer continuity must fail.
                    px, py = config.pitch_x_mm, config.pitch_y_mm
                    broken = part.cut(Solid.make_box(8., .3, config.height_mm,
                        Plane(origin=(px-4., py+2., config.floor_top_mm+.1))))
                    self.assertEqual(len(broken.solids()), 1)
                    bad = junction_layer_samples(broken, config, config.components[0])
                    self.assertFalse(all(sample['passed'] for sample in bad), bad)

    def test_partial_concave_regions_keep_shared_floor_and_empty_missing_cells(self):
        config = BinConfiguration(container_type='drawer', cells=((0,0),(1,0),(0,1),(2,2)),
            wall_perimeters=1, dividers=({'axis':'x','x':1,'y':0},))
        parts = build_bins(config)
        self.assertEqual(tuple(parts), ('bin_01','bin_02'))
        first, second = parts.values()
        px, py = config.pitch_x_mm, config.pitch_y_mm
        self.assertTrue(first.is_inside((px, py/2, config.floor_top_mm-.1)))
        self.assertTrue(first.is_inside((px/2, py, config.floor_top_mm-.1)))
        self.assertFalse(first.is_inside((px/2, py, config.floor_top_mm+5)))
        self.assertTrue(first.is_inside((px, py/2, config.floor_top_mm+5)))
        for part in parts.values():
            self.assertTrue(part.is_valid)
            self.assertEqual((len(part.solids()), len(part.shells())), (1,1))
            self.assertAlmostEqual(part.bounding_box().min.Z, 0., places=6)
            self.assertFalse(part.is_inside((1.5*px, 1.5*py, config.floor_top_mm-.1)))
        self.assertLess(intersection_volume(first, second), 1e-6)
        samples = normal_wall_samples(first, config)
        self.assertGreaterEqual(len(samples), 4)
        self.assertTrue(all(sample['passed'] for sample in samples), samples)

    def test_m5_2f_uses_plain_drawer_cavity_with_footless_relief_and_rim_clearance(self):
        config = BinConfiguration(container_type='drawer', family='M', depth_units=5,
                                  height_units=2, drawer_floor=3., wall_perimeters=2)
        self.assertEqual((config.columns, config.rows), (4,5))
        parts = build_bins(config)
        part = parts['bin_01']
        bounds = part.bounding_box()
        self.assertAlmostEqual(bounds.min.X, .25, places=6)
        self.assertAlmostEqual(bounds.max.X, config.width_mm-.25, places=6)
        self.assertAlmostEqual(bounds.min.Y, .25, places=6)
        self.assertAlmostEqual(bounds.max.Y, config.depth_mm-.25, places=6)
        self.assertAlmostEqual(bounds.min.Z, 0., places=6)
        # The relieved lower edge clears the drawer's R1 floor fillet while
        # retaining its full usable width above the first 0.75 mm.
        self.assertFalse(part.is_inside((.4, config.depth_mm/2, .1)))
        self.assertTrue(part.is_inside((.4, config.depth_mm/2, 1.)))
        self.assertTrue(part.is_inside((config.width_mm/2, config.depth_mm/2, 1.1)))
        self.assertFalse(part.is_inside((config.width_mm/2, config.depth_mm/2, 1.3)))
        report = audit_drawer_bins(config, parts)
        self.assertTrue(report['passed'], report)
        self.assertAlmostEqual(report['rim_clearance_mm'], 1., places=6)
        self.assertAlmostEqual(report['positive_control_shift_x_mm'], 1., places=6)
        self.assertGreater(report['shifted_collision_mm3'], .1)
        self.assertGreater(report['lowered_collision_mm3'], .1)


if __name__ == '__main__':
    unittest.main()
