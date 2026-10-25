"""Preserve measured slide sections, depth stations, and print orientation."""
import unittest

from vault.runner_slides import RunnerSlideSpec, build_runner_slide, build_runner_slides


class RunnerSlideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = {d: build_runner_slide(spec=RunnerSlideSpec(d)) for d in (3, 4, 7)}

    def test_reference_dimensions_volumes_and_solid_integrity(self):
        references = {3: (118, 14916.6421237), 4: (160, 20145.1344910),
                      7: (286, 35827.4023578)}
        for depth, (length, volume) in references.items():
            shape = self.parts[depth]
            with self.subTest(depth=depth):
                self.assertTrue(shape.is_valid)
                self.assertEqual(len(shape.solids()), 1)
                self.assertEqual(len(shape.shells()), 1)
                b = shape.bounding_box()
                self.assertAlmostEqual(b.size.X, 18.2207, delta=.001)
                self.assertAlmostEqual(b.size.Y, length, delta=.000001)
                self.assertAlmostEqual(b.min.Z, 0, delta=.000001)
                self.assertAlmostEqual(b.max.Z, 8.979, delta=.000002)
                self.assertLess(abs(shape.volume / volume - 1), .001)

    def test_mating_profile_keeps_rounded_flange_and_dovetail(self):
        for depth, shape in self.parts.items():
            with self.subTest(depth=depth):
                self.assertTrue(shape.is_inside((8.5, 30, 1.4)))
                self.assertFalse(shape.is_inside((8.5, 30, 2.8)))
                self.assertTrue(shape.is_inside((5.5, 30, 8.95)))
                self.assertFalse(shape.is_inside((5.5, 30, 7.7)))
                self.assertTrue(shape.is_inside((4.8, 30, 7.7)))
                tail = {3: 108, 4: 150, 7: 276}[depth]
                self.assertFalse(shape.is_inside((7.1, tail, .1)))
                self.assertTrue(shape.is_inside((7.1, tail, 1.4)))

    def test_head_stop_and_half_length_flange_end(self):
        # Independent source measurements, not the constructor's formula.
        ends = {3: 72.1093, 4: 93.1093, 7: 156.1093}
        for depth, end in ends.items():
            shape = self.parts[depth]
            with self.subTest(depth=depth):
                self.assertTrue(shape.is_inside((8, 4, 6)))
                self.assertFalse(shape.is_inside((8, 10, 6)))
                self.assertTrue(shape.is_inside((8, end-2, 1.4)))
                self.assertFalse(shape.is_inside((8, end+2, 1.4)))
                self.assertTrue(shape.is_inside((0, end+.2, .1)))
                self.assertTrue(shape.is_inside((0, end+.2, .3)))

    def test_underside_is_flat_across_flange_transition(self):
        for depth, shape in self.parts.items():
            end = RunnerSlideSpec(depth).flange_end
            for x in (-5, 0, 5):
                for offset in (-.1, .1, .2, .3, .5):
                    with self.subTest(depth=depth, x=x, offset=offset):
                        self.assertTrue(shape.is_inside((x, end+offset, .01)))
                        self.assertFalse(shape.is_inside((x, end+offset, -.01)))

    def test_pair_is_identical_and_specs_reject_unsupported_depths(self):
        pair = build_runner_slides(spec=RunnerSlideSpec(3))
        self.assertEqual(set(pair), {'left', 'right'})
        self.assertAlmostEqual(pair['left'].volume, pair['right'].volume, places=7)
        for depth in range(3, 8):
            spec = RunnerSlideSpec(depth)
            self.assertEqual(spec.slug, f'x{depth}_runner_slides')
            self.assertEqual(spec.name, f'x{depth} Runner Slides')
        for depth in (2, 8, True, 4.0, '4', None):
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                RunnerSlideSpec(depth)
        with self.assertRaises(TypeError):
            build_runner_slide(spec='x4')

    def test_nose_crown_has_clearance_chamfer(self):
        for depth in range(3, 8):
            shape = build_runner_slide(spec=RunnerSlideSpec(depth))
            with self.subTest(depth=depth):
                # At Y=.548 the new 45 degree face is Z=8.479.
                self.assertTrue(shape.is_inside((0, .548, 8.429)))
                self.assertFalse(shape.is_inside((0, .548, 8.529)))
                self.assertFalse(shape.is_inside((0, .1, 8.95)))
                self.assertTrue(shape.is_inside((0, 1.1, 8.95)))
                self.assertTrue(shape.is_inside((8, 4, 6)))


if __name__ == '__main__':
    unittest.main()
