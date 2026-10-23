"""Regression checks for independent pocket datums and coupled corner controls."""
from dataclasses import replace
import unittest

from build123d import Axis, Plane, Solid

from vault.envelope import EnvelopeDimensions
from vault.shell import ShellDimensions, _mouth_pockets, _runner_profile
from vault.spec import DEFAULT_SPEC


class FeatureParameterTests(unittest.TestCase):
    def test_invalid_corner_controls_fail_before_cad_construction(self):
        defaults = EnvelopeDimensions()
        for changes in (
            {'corner_height': 13},
            {'corner_height': 11},
            {'corner_width': 0},
            {'corner_first_radius': float('inf')},
            {'corner_turns': (.5, .4, 1.2)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(defaults, **changes)

    def test_pocket_floor_moves_relief_and_entry_lip_in_solid_wall(self):
        dimensions = ShellDimensions()
        block = Solid.make_box(14, 8, 47, Plane(origin=(-80, 181, 0)))
        inner = DEFAULT_SPEC.half_width - dimensions.channel_inner_inset
        runner = _runner_profile(
            dimensions.back_wall, dimensions.channel_floor,
            dimensions.channel_ceiling, dimensions.channel_back_radius,
            DEFAULT_SPEC.depth, dimensions.channel_mouth_radius,
            lambda y, z: (-inner, y, z),
        )
        width = dimensions.channel_inner_inset - dimensions.channel_outer_inset
        wall = block.cut(Solid.extrude(runner, (-width, 0, 0)))

        def section_heights(floor, y):
            cutters = _mouth_pockets(
                DEFAULT_SPEC, replace(dimensions, pocket_floor=floor), 0,
            )
            result = wall.cut(*cutters[:2]).clean()
            self.assertTrue(result.is_valid)
            intersections = result.find_intersection_points(
                Axis((-70.3344, y, -1), (0, 0, 1)),
            )
            return sorted({round(point.Z, 8) for point, _ in intersections})

        for y, nominal_floor in ((185, 6.4914), (187.5, 8.6478)):
            with self.subTest(y=y):
                nominal = section_heights(dimensions.pocket_floor, y)
                lowered = section_heights(dimensions.pocket_floor - .4, y)
                self.assertEqual(len(nominal), 4)
                self.assertEqual(len(lowered), 4)
                self.assertAlmostEqual(nominal[1], nominal_floor, places=6)
                self.assertAlmostEqual(lowered[1], nominal_floor - .4, places=6)
                self.assertEqual(nominal[2:], lowered[2:])


if __name__ == '__main__':
    unittest.main()
