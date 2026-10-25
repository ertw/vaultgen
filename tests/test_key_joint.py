"""Fit, registration, retention, and support-free roofs of the key joint."""

import math
import unittest

import numpy as np
from build123d import Axis, Compound, Solid

from vault.key import KeyDimensions, _joint, build_key_parts


def _shape(result):
    # OpenCascade returns a ShapeList for disconnected boolean results.
    if result is None:
        return Compound(children=[])
    return Compound(children=list(result)) if isinstance(result, list) else result


class KeyJointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for clearance in (.10, .20, .30):
            dimensions = KeyDimensions(clearance=clearance)
            male, socket, _ = _joint(dimensions)
            above_split = Solid.make_box(40, 40, 30).translate(
                (-20, -20, dimensions.split_z))
            cls.cases.append((dimensions, male, socket, above_split))

    def interference(self, part, socket, above_split):
        return _shape(_shape(part.intersect(above_split)).cut(socket)).volume

    def test_all_supported_clearances_assemble_without_interference(self):
        for dimensions, male, socket, above_split in self.cases:
            with self.subTest(clearance=dimensions.clearance):
                for part in male:
                    self.assertLess(self.interference(part, socket, above_split), 1e-7)

    def test_registration_blocks_reversed_and_quarter_turn_assembly(self):
        for dimensions, male, socket, above_split in self.cases:
            for angle in (90, 180, 270):
                with self.subTest(clearance=dimensions.clearance, angle=angle):
                    wrong_way = male[0].rotate(Axis.Z, angle)
                    self.assertGreater(self.interference(wrong_way, socket, above_split), .1)

    def test_hooks_allow_specified_play_then_require_flex_to_withdraw(self):
        for dimensions, male, socket, above_split in self.cases:
            for beam in male[1:]:
                with self.subTest(clearance=dimensions.clearance):
                    free = beam.translate((0, 0, -dimensions.axial_clearance + .01))
                    retained = beam.translate((0, 0, -dimensions.axial_clearance - .05))
                    self.assertLess(self.interference(free, socket, above_split), 1e-7)
                    self.assertGreater(self.interference(retained, socket, above_split), .001)

    def test_socket_ceilings_are_at_least_45_degrees(self):
        # Up-facing cutter surfaces become down-facing ceilings in the handle.
        # A horizontal blind-pocket ceiling would fail this check.
        for dimensions, male, socket, above_split in self.cases:
            with self.subTest(clearance=dimensions.clearance):
                for face in socket.faces():
                    self.assertLessEqual(face.normal_at().Z, math.sqrt(.5) + 1e-7)


class KeyAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = build_key_parts()

    def test_print_parts_are_two_connected_solids_resting_on_the_bed(self):
        self.assertEqual(set(self.parts), {'gear', 'handle'})
        for name, part in self.parts.items():
            with self.subTest(part=name):
                self.assertTrue(part.is_valid)
                self.assertEqual(len(part.solids()), 1)
                self.assertEqual(len(part.shells()), 1)
                self.assertAlmostEqual(part.bounding_box().min.Z, 0, places=6)
                self.assertIsNone(part.parent, 'Print parts must export independently')

    def test_print_parts_reassemble_without_material_overlap(self):
        dimensions = KeyDimensions()
        gear = self.parts['gear']
        handle = self.parts['handle'].translate((0, 0, dimensions.split_z))
        self.assertAlmostEqual(gear.bounding_box().max.Z,
                               dimensions.split_z + dimensions.beam_height, places=5)
        self.assertLess(_shape(gear.intersect(handle)).volume, 1e-6)
        self.assertAlmostEqual(gear.distance_to(handle), 0, places=6)

    def test_gear_transition_has_no_steeper_than_45_degree_underside(self):
        # A loft between unequal edge counts can be valid CAD yet warp between
        # the two outlines, leaving unsupported patches on the tooth bevel.
        vertices, faces = self.parts['gear'].tessellate(.01, .1)
        triangles = np.asarray([tuple(vertex) for vertex in vertices])[faces]
        normals = np.cross(triangles[:, 1] - triangles[:, 0],
                           triangles[:, 2] - triangles[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        centers = triangles.mean(axis=1)
        selected = (centers[:, 2] > 6.40001) & (centers[:, 2] < 7.39999) & (lengths > 1e-12)
        self.assertTrue(selected.any())
        normal_z = normals[selected, 2] / lengths[selected]
        self.assertGreaterEqual(normal_z.min(), -math.sqrt(.5) - 1e-4)


if __name__ == '__main__':
    unittest.main()
