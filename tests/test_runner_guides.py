"""Independent source dimensions and functional runner guide interfaces."""

import unittest

from vault.runner_guides import RunnerGuideSpec, build_runner_guide, build_runner_guides


class RunnerGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shapes = {depth: build_runner_guide(spec=RunnerGuideSpec(depth))
                      for depth in range(3, 8)}

    def test_all_source_depths_preserve_envelope_volume_and_connectivity(self):
        # Independent measurements of the first connected part in each STL.
        volumes = {3: 21068.78296, 4: 27276.46275, 5: 33524.59443,
                   6: 39772.20110, 7: 46020.09692}
        lengths = {3: 143.5, 4: 185.5, 5: 227.5, 6: 269.5, 7: 311.5}
        for depth, shape in self.shapes.items():
            with self.subTest(depth=depth):
                self.assertTrue(shape.is_valid)
                self.assertEqual(len(shape.solids()), 1)
                self.assertEqual(len(shape.shells()), 1)
                bounds = shape.bounding_box()
                for actual, expected in zip(tuple(bounds.min), (0, 0, 0)):
                    self.assertAlmostEqual(actual, expected, delta=.001)
                for actual, expected in zip(tuple(bounds.max), (27, lengths[depth], 9.4)):
                    self.assertAlmostEqual(actual, expected, delta=.001)
                self.assertLess(abs(shape.volume-volumes[depth])/volumes[depth], .0003)

    def test_bearing_channel_and_retaining_lip_match_source_sections(self):
        shape = self.shapes[4]
        # Rear open channel at Y80; retained female T section at Y150.
        self.assertTrue(shape.is_inside((3.8, 80, 6.2)))
        self.assertFalse(shape.is_inside((4.1, 80, 6.2)))
        self.assertFalse(shape.is_inside((5.8, 80, 8.0)))
        self.assertTrue(shape.is_inside((5.8, 150, 8.0)))
        self.assertFalse(shape.is_inside((6.3, 150, 8.0)))
        self.assertTrue(shape.is_inside((13.5, 150, 4.5)))
        self.assertFalse(shape.is_inside((13.5, 150, 4.7)))
        self.assertFalse(shape.is_inside((5.8, 184.8, 8.0)))
        self.assertTrue(shape.is_inside((5.8, 182, 8.0)))

    def test_travel_slot_end_and_lip_transition_preserve_short_depth_exception(self):
        # Source capsule end centers and lip starts progress by half a depth
        # unit, with the x3 original one millimetre shorter than that sequence.
        for depth, slot_end, lip_start in ((3, 105.458, 98.65), (4, 127.458, 120.65),
                                            (5, 148.458, 141.65), (6, 169.458, 162.65),
                                            (7, 190.458, 183.65)):
            with self.subTest(depth=depth):
                shape = self.shapes[depth]
                self.assertFalse(shape.is_inside((13.5, slot_end+3.4, 1)))
                self.assertTrue(shape.is_inside((13.5, slot_end+3.7, 1)))
                self.assertFalse(shape.is_inside((5.8, lip_start-.2, 8)))
                self.assertTrue(shape.is_inside((5.8, lip_start+.2, 8)))
                self.assertTrue(shape.is_inside((9.7, 40, 3)))
                self.assertFalse(shape.is_inside((10.1, 40, 3)))

    def test_pair_has_two_identical_printable_guides(self):
        pair = build_runner_guides(spec=RunnerGuideSpec(3))
        self.assertEqual(set(pair), {"left", "right"})
        self.assertAlmostEqual(pair["left"].volume, pair["right"].volume, places=6)
        self.assertEqual(RunnerGuideSpec(7).slug, "x7_runner_guides")

    def test_depth_input_is_strict_and_bounded(self):
        for value in (True, False, 2, 8, 4.0, "4", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RunnerGuideSpec(value)


if __name__ == "__main__":
    unittest.main()
