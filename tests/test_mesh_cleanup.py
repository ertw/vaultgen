"""Focused checks for the bounded STL tessellation repair."""

import json
import unittest

import numpy as np
import trimesh

from vault.mesh_cleanup import close_micro_triangles


def tetrahedron(span=0.00004, closed=False):
    vertices = [[0, 0, 0], [span, 0, 0], [0, span, 0], [0, 0, 1]]
    faces = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    return trimesh.Trimesh(vertices, faces if closed else faces[1:], process=False)


def tetrahedron_with_t_junction(span=0.0008):
    mesh = tetrahedron(span, closed=True)
    mesh.vertices = np.vstack((mesh.vertices, (mesh.vertices[0] + mesh.vertices[1]) / 2))
    mesh.faces = np.vstack((mesh.faces[[0, 2, 3]], [[0, 4, 3], [4, 1, 3]]))
    return mesh


class MicroTriangleTests(unittest.TestCase):
    def test_closes_only_missing_micro_triangle_without_moving_vertices(self):
        mesh = tetrahedron()
        vertices, faces = mesh.vertices.copy(), mesh.faces.copy()
        report = close_micro_triangles(mesh)
        self.assertEqual(report["triangles_added"], 1)
        self.assertEqual(report["boundary_edges_after"], 0)
        self.assertLess(report["max_repaired_diameter_mm"], 0.0001)
        self.assertTrue(mesh.is_watertight)
        self.assertTrue(mesh.is_winding_consistent)
        np.testing.assert_array_equal(mesh.vertices, vertices)
        np.testing.assert_array_equal(mesh.faces[:len(faces)], faces)
        self.assertAlmostEqual(mesh.volume, tetrahedron(closed=True).volume, places=16)
        json.dumps(report)

    def test_leaves_larger_triangle_open(self):
        mesh = tetrahedron(span=0.004)
        report = close_micro_triangles(mesh)
        self.assertEqual(report["triangles_added"], 0)
        self.assertEqual(report["boundary_edges_after"], 3)
        self.assertFalse(mesh.is_watertight)

    def test_closes_triangle_below_chord_tolerance(self):
        mesh = tetrahedron(span=0.0035)
        report = close_micro_triangles(mesh)
        self.assertEqual(report["missing_triangles_filled"], 1)
        self.assertEqual(report["t_junctions_split"], 0)
        self.assertLess(report["max_repaired_diameter_mm"], 0.005)
        self.assertTrue(mesh.is_watertight)

    def test_splits_collinear_t_junction_without_changing_geometry(self):
        mesh = tetrahedron_with_t_junction()
        vertices, volume, area = mesh.vertices.copy(), mesh.volume, mesh.area
        report = close_micro_triangles(mesh)
        self.assertEqual(report["missing_triangles_filled"], 0)
        self.assertEqual(report["t_junctions_split"], 1)
        self.assertEqual(report["boundary_edges_after"], 0)
        self.assertTrue(mesh.is_watertight)
        self.assertTrue(mesh.is_winding_consistent)
        self.assertTrue(np.all(mesh.area_faces > 0))
        np.testing.assert_array_equal(mesh.vertices, vertices)
        self.assertAlmostEqual(mesh.volume, volume, places=16)
        self.assertAlmostEqual(mesh.area, area, places=16)

    def test_leaves_larger_t_junction_open(self):
        mesh = tetrahedron_with_t_junction(span=0.006)
        faces = mesh.faces.copy()
        report = close_micro_triangles(mesh)
        self.assertEqual(report["triangles_added"], 0)
        self.assertEqual(report["boundary_edges_after"], 3)
        np.testing.assert_array_equal(mesh.faces, faces)

    def test_leaves_tiny_four_edge_hole_open(self):
        s = 0.00002
        mesh = trimesh.Trimesh(
            [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [s/2, s/2, 1]],
            [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], process=False,
        )
        report = close_micro_triangles(mesh)
        self.assertEqual(report["triangles_added"], 0)
        self.assertEqual(report["boundary_edges_after"], 4)
        self.assertFalse(mesh.is_watertight)

    def test_leaves_branched_boundary_open(self):
        first = tetrahedron()
        second = tetrahedron()
        second.vertices *= [-1, -1, 1]
        # Two holes share vertex 0, giving one six-edge boundary component.
        vertices = np.vstack((first.vertices, second.vertices[1:]))
        mapping = np.array([0, 4, 5, 6])
        mesh = trimesh.Trimesh(vertices, np.vstack((first.faces, mapping[second.faces])), process=False)
        report = close_micro_triangles(mesh)
        self.assertEqual(report["triangles_added"], 0)
        self.assertEqual(report["boundary_edges_after"], 6)

    def test_leaves_inconsistently_wound_boundary_open(self):
        mesh = tetrahedron()
        mesh.faces[0] = mesh.faces[0][::-1]
        report = close_micro_triangles(mesh)
        self.assertEqual(report["triangles_added"], 0)
        self.assertEqual(report["boundary_edges_after"], 3)

    def test_closed_mesh_unchanged(self):
        mesh = tetrahedron(closed=True)
        faces = mesh.faces.copy()
        report = close_micro_triangles(mesh)
        self.assertEqual(report["triangles_added"], 0)
        self.assertEqual(report["boundary_edges_before"], 0)
        np.testing.assert_array_equal(mesh.faces, faces)


if __name__ == "__main__":
    unittest.main()
