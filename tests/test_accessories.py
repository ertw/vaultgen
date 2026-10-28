"""Accessory geometry and universal cache identity regressions."""
import unittest
from vault.accessories import (SpringDimensions, build_spring, build_facade_cap,
                               build_key_cap, build_runner_stop)
from vault.generator import Configuration, ACCESSORY_PARTS
from vault.build import select_spec


class AccessoryTests(unittest.TestCase):
    def test_latch_relief_preserves_connected_arms_and_finger_opening(self):
        from vault.latch import LatchDimensions, build_latch
        nominal = build_latch(LatchDimensions(0, 0))
        loose = build_latch()
        self.assertTrue(loose.is_valid)
        self.assertEqual(len(loose.solids()), 1)
        self.assertLess(loose.volume, nominal.volume)
        self.assertLess(sum(s.volume for s in loose.cut(nominal)), 1e-6)
        self.assertAlmostEqual(loose.bounding_box().size.Z, 4.35, places=5)
        self.assertFalse(loose.is_inside((0, -24.839, 2)))
        for x in (-37,37):
            self.assertTrue(loose.is_inside((x, 30, 2)))

    def test_latch_offset_surfaces_survive_step_roundtrip(self):
        import tempfile
        from pathlib import Path
        from build123d import export_step
        from vault.latch import build_latch
        from vault.exports import check_step
        latch = build_latch()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'latch.step'
            self.assertTrue(export_step(latch, path))
            _, report = check_step(latch, path)
            self.assertTrue(report['passed'])

    def test_latch_window_retains_side_webs_and_solid_v_seat(self):
        from vault.latch import build_latch
        latch = build_latch()
        # The opening reaches from the finger ring toward the V without
        # breaking the side webs, the pull edge, or the bridge above the V.
        for z in (.1, 2.175, 4.25):
            for y in (-30, -24.839, -10, 0, 8, 10.5):
                self.assertFalse(latch.is_inside((0, y, z)), (y, z))
            for x in (-4, 4):
                for y in (0, 5, 10):
                    self.assertTrue(latch.is_inside((x, y, z)), (x, y, z))
            for y in (-35, 14, 17):
                self.assertTrue(latch.is_inside((0, y, z)), (y, z))
        # The previous relieved part occupied 9488 mm³. Keep a meaningful
        # material reduction while protecting against an accidentally empty web.
        self.assertGreater(latch.volume, 8000)
        self.assertLess(latch.volume, 8500)
        for face in latch.faces():
            if face.bounding_box().size.Z < 1e-5 and face.inner_wires():
                # The full vertical webs remain; the larger top round retreats
                # both upper edges while the lower chamfer remains unchanged.
                minimum = 3.0 if abs(face.center().Z) < 1e-5 else 2.3
                self.assertGreaterEqual(face.outer_wire().distance_to(face.inner_wires()[0]), minimum)

    def test_latch_finger_aperture_retains_lower_chamfer_and_rounded_top(self):
        from vault.latch import build_latch
        latch = build_latch()
        for x in (-7.5, 7.5):
            self.assertFalse(latch.is_inside((x, -24.839, 2.175)))
        for x in (-7.9, 7.9):
            self.assertTrue(latch.is_inside((x, -24.839, 2.175)))
            self.assertFalse(latch.is_inside((x, -24.839, .1)))
            self.assertFalse(latch.is_inside((x, -24.839, 4.25)))
        # A quarter-circle round retains more material halfway up the blend
        # than a same-sized chamfer, while opening out at the very top.
        for x in (-7.906, 7.906):
            self.assertTrue(latch.is_inside((x, -24.839, 4.1)))
            self.assertFalse(latch.is_inside((x, -24.839, 4.34)))
        for x in (-8.2, 8.2):
            for z in (.1, 2.175, 4.25):
                self.assertTrue(latch.is_inside((x, -24.839, z)))

    def test_latch_rejects_chamfers_that_consume_the_side_webs(self):
        from vault.latch import LatchDimensions
        for value in (-.01, .31, float('nan'), float('inf'), True, '0.3'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LatchDimensions(opening_chamfer=value)

    def test_latch_top_fillet_dimensions_accept_half_millimeter_and_reject_invalid_values(self):
        from vault.latch import LatchDimensions
        self.assertEqual(LatchDimensions().top_fillet_radius, .5)
        for value in (-.01, .51, float('nan'), float('inf'), True, '0.5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LatchDimensions(top_fillet_radius=value)

    def test_latch_remains_connected_at_supported_relief_limits(self):
        from vault.latch import LatchDimensions, build_latch
        # At maximum research relief the tiny insertion tips cannot accept
        # the default round. Keep that envelope available with rounding off.
        for dimensions in (LatchDimensions(.25, .25, top_fillet_radius=0),
                           LatchDimensions(opening_chamfer=0)):
            with self.subTest(dimensions=dimensions):
                latch = build_latch(dimensions)
                self.assertTrue(latch.is_valid)
                self.assertEqual(len(latch.solids()), 1)
                self.assertEqual(len(latch.shells()), 1)

    def test_latch_top_fillet_preserves_flat_bed_and_print_height(self):
        from vault.latch import LatchDimensions, build_latch
        rounded = build_latch()
        sharp = build_latch(LatchDimensions(top_fillet_radius=0))
        def bed_area(shape):
            return sum(face.area for face in shape.faces()
                       if face.bounding_box().size.Z < 1e-5 and abs(face.center().Z) < 1e-5)
        self.assertAlmostEqual(bed_area(rounded), bed_area(sharp), places=5)
        self.assertAlmostEqual(rounded.bounding_box().min.Z, 0, places=5)
        self.assertAlmostEqual(rounded.bounding_box().max.Z, 4.35, places=5)
        self.assertLess(rounded.volume, sharp.volume)

    def test_latch_top_fillet_has_a_checked_watertight_print_mesh(self):
        from vault.latch import build_latch
        from vault.tessellation import review_mesh
        mesh = review_mesh(build_latch())
        self.assertTrue(mesh.is_watertight)
        self.assertTrue(mesh.is_winding_consistent)
        self.assertGreater(mesh.volume, 0)

    def test_spring_defaults_are_nominal(self):
        self.assertEqual(SpringDimensions(), SpringDimensions(0, 0))
        self.assertAlmostEqual(build_spring().bounding_box().size.Z, 5.155, places=5)

    def test_universal_specs_do_not_depend_on_drawer_size(self):
        for kind in ACCESSORY_PARTS:
            self.assertEqual(select_spec(kind,'S',3,1),select_spec(kind,'L',7,2))
            self.assertEqual(Configuration(part=kind).parts,(kind,))

    def test_relief_removes_material_without_scaling_spring(self):
        nominal=build_spring(SpringDimensions(0,0))
        loose=build_spring(SpringDimensions(.10,.15))
        self.assertLess(loose.volume,nominal.volume)
        self.assertLess(sum(s.volume for s in loose.cut(nominal)),1e-6)
        self.assertAlmostEqual(loose.bounding_box().max.Z,5.005,places=5)
        for p in [(-14,0,.5),(-8,0,.5),(4,0,.5),(22,0,.5)]:
            self.assertTrue(loose.is_inside(p))
        for p in [(-11,0,.5),(-5,0,.5),(1,0,.5),(15,0,.5)]:
            self.assertFalse(loose.is_inside(p))

    def test_caps_keep_closed_faces_and_open_sockets(self):
        for build in (build_facade_cap,build_key_cap):
            cap=build()
            self.assertTrue(cap.is_valid)
            self.assertEqual(len(cap.solids()),1)
            self.assertTrue(cap.is_inside((0,0,.5)))
            self.assertFalse(cap.is_inside((0,0,2.1)))

    def test_stop_retains_split_and_connected_flange(self):
        stop=build_runner_stop()
        self.assertTrue(stop.is_inside((0,0,.4)))
        self.assertFalse(stop.is_inside((0,0,4)))
        self.assertTrue(stop.is_inside((2,0,4)))
        self.assertEqual(len(stop.solids()),1)

if __name__=='__main__':unittest.main()
