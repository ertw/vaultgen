"""Geometric assembly checks for the keyed, blind PLA facade joint."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from build123d import Plane, Solid, export_step

from vault.__main__ import print_orientation
from vault.box import build_box
from vault.exports import check_step, precise_volume
from vault.facade import build_facade
from vault.printed_joint import (
    D, BOX_SPEC, FACADE_SPEC, SCREW_SPEC,
    build_printed_box, build_printed_facade, build_printed_screw, placed_screw,
)
from tools.check_printed_joint import inspect_joint, intersection_volume


class PrintedJointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box = build_printed_box()
        cls.facade = build_printed_facade()
        cls.screw = build_printed_screw()
        cls.motion = inspect_joint(cls.box, cls.facade)

    def test_parts_are_connected_valid_solids_in_their_print_orientations(self):
        for shape, spec in ((self.box, BOX_SPEC), (self.facade, FACADE_SPEC),
                            (self.screw, SCREW_SPEC)):
            with self.subTest(part=spec.slug):
                self.assertTrue(shape.is_valid)
                self.assertEqual(len(shape.solids()), 1)
                self.assertEqual(len(shape.shells()), 1)
                printable = print_orientation(shape, spec)
                self.assertAlmostEqual(printable.bounding_box().min.Z, 0, places=6)
                self.assertAlmostEqual(printable.volume, shape.volume, places=5)

    def test_insertion_rotation_and_stops(self):
        for name,passed in self.motion['checks'].items():
            with self.subTest(check=name):self.assertTrue(passed,self.motion)

    def test_head_is_recessed_and_plain(self):
        from math import sin,cos,radians
        self.assertAlmostEqual(D.head_radius,7)
        for angle in range(0,360,15):
            a=radians(angle)
            self.assertTrue(self.screw.is_inside((6.9*cos(a),-1,6.9*sin(a))))
        head_back=D.locked_head_y-D.head_thickness
        self.assertGreaterEqual(head_back,D.box_seat)
        self.assertGreaterEqual(head_back-self.motion['axial_clearance']['thread_pullout']['free_mm'],D.box_seat-.001)
        for x in (-D.axis_x,D.axis_x):
            self.assertFalse(self.box.is_inside((x+7.1,183,D.axis_z)))
            self.assertTrue(self.box.is_inside((x+7.5,183,D.axis_z)))

    def test_shallow_locating_seat_and_remaining_web(self):
        self.assertEqual(D.pilot_length,1)
        for x in (-D.axis_x,D.axis_x):
            self.assertFalse(self.box.is_inside((x+6,187,D.axis_z)))
            self.assertTrue(self.box.is_inside((x+6,186,D.axis_z)))
            self.assertAlmostEqual((D.facade_seat-D.pilot_length-.2)-D.head_seat,1.7)

    def test_close_shank_bore_and_bottom_keyway(self):
        y=186
        for x in (-D.axis_x,D.axis_x):
            self.assertFalse(self.box.is_inside((x+4.2,y,D.axis_z)))
            self.assertTrue(self.box.is_inside((x+4.4,y,D.axis_z)))
            self.assertFalse(self.box.is_inside((x,y,D.axis_z-5.3)))
            self.assertTrue(self.box.is_inside((x,y,D.axis_z+5.3)))
            self.assertTrue(self.box.is_inside((x+1.5,y,D.axis_z-5.3)))

    def test_lug_has_positive_side_draft(self):
        # Tangential width becomes narrower toward the outside of the lug;
        # a side tool can withdraw without a dovetail undercut.
        import math
        y=D.lug_y+D.lead*15/360
        def width_at(z):
            inside=[i/1000 for i in range(0,1501) if self.screw.is_inside((i/1000,y,-z))]
            return max(inside)
        self.assertGreater(width_at(4.2),width_at(5.2)+.1)

    def test_no_spring_or_auxiliary_appendage(self):
        outer=Solid.make_cylinder(8,2,Plane(origin=(0,.05,0),z_dir=(0,1,0)))
        inner=Solid.make_cylinder(4.05,2.2,Plane(origin=(0,0,0),z_dir=(0,1,0)))
        self.assertLess(intersection_volume(self.screw,outer.cut(inner)),1e-5)
        self.assertTrue(self.screw.is_inside((0,-2.8,5)))

    def test_blind_facade_and_pilot_compatibility(self):
        self.assertLess(intersection_volume(self.box,self.facade.translate((0,D.facade_seat,0))),1e-5)
        for x in (-D.axis_x,D.axis_x):
            for y in (6.1,7,7.8):self.assertTrue(self.facade.is_inside((x,y,D.axis_z)))
        self.assertLess(placed_screw(angle=D.turn).bounding_box().max.Y,D.facade_seat+D.blind_depth)

    def test_default_steel_hardware_variants_keep_their_existing_bores(self):
        original_box, original_facade = build_box(), build_facade()
        for x in (-D.axis_x, D.axis_x):
            self.assertFalse(original_box.is_inside((x, 183, D.axis_z)))
            self.assertTrue(original_box.is_inside((x+3, 183, D.axis_z)))
            self.assertFalse(original_facade.is_inside((x, 3, D.axis_z)))
            self.assertTrue(original_facade.is_inside((x+3, 3, D.axis_z)))
            self.assertFalse(original_facade.is_inside((x, 7, D.axis_z)))
        for actual, expected in zip(original_box.bounding_box().size, (134.2,185.8,37.5)):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_screw_survives_step_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'printed_screw.step'
            self.assertTrue(export_step(self.screw, path))
            restored, report = check_step(self.screw, path)
            self.assertTrue(report['passed'])
            self.assertEqual(len(restored.shells()), 1)

    def test_coin_recess_curves_up_to_surface_and_keeps_deeper_flathead_engagement(self):
        # Probe both sides of the curved floor across the full slot width.
        # The shallow scoop meets the head surface at X=+/-6.
        from math import sqrt
        for side in (-1, 1):
            for x in (3.2, 5, 5.8):
                floor_y = -17.4 + sqrt(15.6**2-x**2)
                for z in (-.6, .6):
                    self.assertFalse(self.screw.is_inside((side*x, floor_y-.03, z)))
                    self.assertTrue(self.screw.is_inside((side*x, floor_y+.03, z)))
            self.assertTrue(self.screw.is_inside((side*6.1, -2.98, 0)))
        # Coin walls draft from 2 mm to the 1.4 mm screwdriver width.
        for y in (-2.99, -2.7, -2.4, -2.1):
            half_width = .7 + (-1.8-y)*.25
            for side in (-1, 1):
                self.assertFalse(self.screw.is_inside((0, y, side*(half_width-.005))))
                self.assertTrue(self.screw.is_inside((0, y, side*(half_width+.005))))
        # The deeper driver slot retains its original width.
        for y in (-1.7, -1, .5):
            self.assertFalse(self.screw.is_inside((0, y, .6)))
            self.assertTrue(self.screw.is_inside((0, y, .8)))
        # Check the blade's full engagement depth across the head/shaft seam,
        # plus the retained floor and sidewalls inside the shaft.
        for y in (-2.4, -1, .5, 1.1):
            for x in (-2.8, 0, 2.8):
                self.assertFalse(self.screw.is_inside((x, y, 0)))
        self.assertTrue(self.screw.is_inside((0, 1.3, 0)))
        self.assertTrue(self.screw.is_inside((0, .5, .8)))

    def test_clearance_controls_reject_unbuildable_or_unindexed_parameters(self):
        for changes in ({'radial_clearance': .1}, {'radial_clearance': .5},
                        {'axial_clearance': .05}, {'axial_clearance': .4},
                        {'lead': 4.0}, {'turn': 180}, {'shaft_radius': float('nan')}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(D, **changes)


if __name__ == '__main__':
    unittest.main()
