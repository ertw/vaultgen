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
