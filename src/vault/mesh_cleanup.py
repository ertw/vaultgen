"""Repair only microscopic, triangular tessellation boundaries.

OpenCascade occasionally omits a triangle whose vertices become almost
coincident in binary STL precision. Collinear three-edge boundaries are
T-junctions and need an existing triangle split at the existing middle vertex.
No vertex moves, merging, or larger boundary fills occur.
"""

from __future__ import annotations

import numpy as np
import trimesh


MAX_MICRO_TRIANGLE_DIAMETER_MM = 0.005


def close_micro_triangles(mesh: trimesh.Trimesh) -> dict[str, int | float]:
    """Close isolated three-edge boundaries within the 0.005 mm chord tolerance.

    Each eligible boundary component must have exactly three distinct vertices
    and edges and consistent directed winding. A nonzero-area hole gets an
    opposing face; a collinear boundary is resolved by splitting its long-edge
    triangle at the existing middle vertex. Other holes and nonmanifold edges
    remain for the caller's watertightness check to reject.
    Return a JSON-serializable audit report, including remaining boundary edges.
    """
    inverse = mesh.edges_unique_inverse
    counts = np.bincount(inverse, minlength=len(mesh.edges_unique))
    boundary_indices = np.flatnonzero(counts[inverse] == 1)
    directed = mesh.edges[boundary_indices]
    adjacency: dict[int, list[int]] = {}
    for index, (a, b) in enumerate(directed):
        adjacency.setdefault(int(a), []).append(index)
        adjacency.setdefault(int(b), []).append(index)

    unseen = set(range(len(directed)))
    additions: list[list[int]] = []
    replacements: dict[int, list[int]] = {}
    fills = 0
    splits = 0
    max_diameter = 0.0
    skipped = 0
    while unseen:
        pending = [unseen.pop()]
        component: list[int] = []
        vertices: set[int] = set()
        while pending:
            edge_index = pending.pop()
            component.append(edge_index)
            for vertex in directed[edge_index]:
                vertex = int(vertex)
                vertices.add(vertex)
                for neighbor in adjacency[vertex]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        pending.append(neighbor)
        if len(component) != 3 or len(vertices) != 3 or any(
            len(adjacency[v]) != 2 for v in vertices
        ):
            skipped += 1
            continue

        a, b = map(int, directed[component[0]])
        c = next(v for v in vertices if v not in (a, b))
        face = [b, a, c]
        expected = {(int(v), int(u)) for u, v in directed[component]}
        actual = {(face[0], face[1]), (face[1], face[2]), (face[2], face[0])}
        points = mesh.vertices[face]
        spans = points - np.roll(points, -1, axis=0)
        diameter = float(np.sqrt(np.max(np.einsum("ij,ij->i", spans, spans))))
        area_vector = np.cross(points[1] - points[0], points[2] - points[0])
        if (
            actual != expected
            or not np.isfinite(diameter)
            or diameter > MAX_MICRO_TRIANGLE_DIAMETER_MM
        ):
            skipped += 1
            continue
        if np.any(area_vector != 0.0):
            additions.append(face)
            fills += 1
        else:
            # A zero-area loop has one long edge opposite two sub-edges.
            # Split the face using that long edge; its surface stays identical.
            component_points = mesh.vertices[directed[component]]
            lengths = np.linalg.norm(component_points[:, 1] - component_points[:, 0], axis=1)
            long_edge_index = component[int(np.argmax(lengths))]
            u, v = map(int, directed[long_edge_index])
            middle = next(vertex for vertex in vertices if vertex not in (u, v))
            direction = mesh.vertices[v] - mesh.vertices[u]
            denominator = float(np.dot(direction, direction))
            fraction = (float(np.dot(mesh.vertices[middle] - mesh.vertices[u], direction))
                        / denominator if denominator else 0.0)
            if not 0.0 < fraction < 1.0:
                skipped += 1
                continue
            face_index = int(mesh.edges_face[boundary_indices[long_edge_index]])
            third = next(int(vertex) for vertex in mesh.faces[face_index]
                         if vertex not in (u, v))
            replacements[face_index] = [u, middle, third]
            additions.append([middle, v, third])
            splits += 1
        max_diameter = max(max_diameter, diameter)

    if additions:
        original_faces = mesh.faces.copy()
        for index, replacement in replacements.items():
            original_faces[index] = replacement
        mesh.faces = np.vstack((original_faces, np.asarray(additions, dtype=np.int64)))
    return {
        "triangles_added": len(additions),
        "missing_triangles_filled": fills,
        "t_junctions_split": splits,
        "max_repaired_diameter_mm": max_diameter,
        "allowed_diameter_mm": MAX_MICRO_TRIANGLE_DIAMETER_MM,
        "boundary_edges_before": len(directed),
        "boundary_edges_after": len(directed) - 3 * len(additions),
        "boundary_components_left_open": skipped,
        "nonmanifold_edges": int(np.count_nonzero(counts > 2)),
    }
