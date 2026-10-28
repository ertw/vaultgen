"""Single-piece key geometry and gear print overhang checks."""
import math
import unittest
import numpy as np
from vault.key import build_key_parts


class KeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = build_key_parts()

    def test_key_is_one_connected_solid_resting_on_the_bed(self):
        self.assertEqual(set(self.parts), {'key'})
        key = self.parts['key']
        self.assertTrue(key.is_valid)
        self.assertEqual(len(key.solids()), 1)
        self.assertEqual(len(key.shells()), 1)
        self.assertAlmostEqual(key.bounding_box().min.Z, 0, places=6)
        # Former split plane and catch/socket region must be filled.
        for z in (7.39, 7.41, 12, 20):
            self.assertTrue(key.is_inside((0, 0, z)))

    def test_gear_transition_has_no_steeper_than_45_degree_underside(self):
        # A loft between unequal edge counts can be valid CAD yet warp between
        # the two outlines, leaving unsupported patches on the tooth bevel.
        vertices, faces = self.parts['key'].tessellate(.01, .1)
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
