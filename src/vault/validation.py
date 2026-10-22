"""Bidirectional surface-distance checks against the unmodified purchased STL."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import numpy as np
import trimesh
from .reference import (SOURCE, DECORATION_BOXES, CLEANUP_PATCHES, decoration_mask,
                        load_reference, mating_region_masks)


def _surface_points(mesh, count, seed):
    points, _ = trimesh.sample.sample_surface(mesh, count, seed=seed)
    # Feature vertices supplement area-weighted samples, which alone can miss
    # narrow lips and short edges. Use all vertices up to the requested count.
    if len(mesh.vertices) > count:
        indices = np.random.default_rng(seed).choice(len(mesh.vertices), count, replace=False)
        vertices = mesh.vertices[indices]
    else:
        vertices = mesh.vertices
    return np.vstack((points, vertices))


def _nearest(mesh, points, batch_size=1500):
    """Exact point/triangle distances using trimesh's bounding-box tree."""
    distances = np.empty(len(points))
    closest = np.empty_like(points)
    for start in range(0, len(points), batch_size):
        stop = min(start + batch_size, len(points))
        closest[start:stop], distances[start:stop], _ = trimesh.proximity.closest_point(mesh, points[start:stop])
    return distances, closest


def _distance_target(mesh):
    """Tighten proximity queries without changing the triangle surface."""
    vertices, faces = trimesh.remesh.subdivide_to_size(
        mesh.vertices, mesh.faces, max_edge=4., max_iter=12
    )
    return trimesh.Trimesh(vertices, faces, process=False)


def _cosmetic_cleanup(mesh, spacing=.5, tolerance=.01):
    """Check that each removed decoration is replaced by its flat skin.

    The comparison masks alone cannot distinguish an unmodified decoration
    from a clean surface. Probe the intended replacement plane throughout each
    rectangle, independently of those masks. ``mesh`` is the already-subdivided
    distance target used by :func:`compare`.
    """
    regions = {}
    # The two small mechanical tabs taper into the underside beside the text.
    # Their measured footprints contain no lettering and must remain raised.
    tab_footprints = [
        [[-16.90, 18.1], [-13.36, 18.96]],
        [[13.36, 18.1], [16.90, 18.96]],
    ]
    for name, (normal_axis, coordinate, first_range, second_range) in CLEANUP_PATCHES.items():
        plane_axes = [axis for axis in range(3) if axis != normal_axis]
        coordinates = [
            np.unique(np.r_[np.linspace(low, high, int(np.ceil((high-low)/spacing))+1), (low+high)/2])
            for low, high in [first_range, second_range]
        ]
        first, second = np.meshgrid(*coordinates, indexing='ij')
        points = np.zeros((first.size, 3), dtype=float)
        points[:, normal_axis] = coordinate
        points[:, plane_axes[0]] = first.ravel()
        points[:, plane_axes[1]] = second.ravel()
        mechanical = np.zeros(len(points), dtype=bool)
        if name == 'align_text_and_arrow':
            for footprint_low, footprint_high in tab_footprints:
                mechanical |= ((points[:, :2] >= footprint_low) & (points[:, :2] <= footprint_high)).all(axis=1)
        points = points[~mechanical]
        distances, _ = _nearest(mesh, points)
        regions[name] = {
            'plane': f'{"XYZ"[normal_axis]}={coordinate:g}',
            'points': len(points),
            'mechanical_tab_points_excluded': int(mechanical.sum()),
            'max_mm': float(distances.max()),
            'over_tolerance': int(np.count_nonzero(~(distances <= tolerance))),
            'passed': bool(np.all(distances <= tolerance)),
        }
    return {
        'method': 'Exact point-to-triangle distance from a regular grid on each intended flat replacement plane.',
        'maximum_grid_spacing_mm': spacing,
        'tolerance_mm': tolerance,
        'mechanical_tab_footprints_xy_mm': tab_footprints,
        'points': sum(region['points'] for region in regions.values()),
        'max_mm': max(region['max_mm'] for region in regions.values()),
        'over_tolerance': sum(region['over_tolerance'] for region in regions.values()),
        'regions': regions,
        'passed': all(region['passed'] for region in regions.values()),
    }


def _summary(points, distances, closest, tolerance):
    worst = np.argsort(distances)[-20:][::-1]
    return {
        'points': len(points),
        'mean_mm': float(distances.mean()),
        'rms_mm': float(np.sqrt(np.mean(distances ** 2))),
        'p50_mm': float(np.percentile(distances, 50)),
        'p95_mm': float(np.percentile(distances, 95)),
        'p99_mm': float(np.percentile(distances, 99)),
        'max_mm': float(distances.max()),
        'over_tolerance': int(np.count_nonzero(distances > tolerance)),
        'fraction_within_tolerance': float(np.mean(distances <= tolerance)),
        'worst_points': [
            {'point': points[i].tolist(), 'nearest': closest[i].tolist(), 'distance_mm': float(distances[i])}
            for i in worst
        ],
    }


def compare(model_path: Path, output: Path, samples=100_000, tolerance=.25, mating_tolerance=.1):
    print('Loading the reference and exported model…', flush=True)
    reference = load_reference()
    model = trimesh.load_mesh(model_path)
    source_points = _surface_points(reference, samples, seed=12345)
    model_points = _surface_points(model, samples, seed=54321)
    source_mask = decoration_mask(source_points)
    model_mask = decoration_mask(model_points)
    source_points = source_points[~source_mask]
    model_points = model_points[~model_mask]
    # Large CAD triangles otherwise give huge query radii. Subdivision changes
    # neither the surface nor its distances; it only tightens the spatial index.
    print('Preparing surface-distance indices…', flush=True)
    target = _distance_target(model)
    reference_target = _distance_target(reference)
    print(f'Comparing {len(source_points):,} reference points to CAD…', flush=True)
    source_distance, source_closest = _nearest(target, source_points)
    print(f'Comparing {len(model_points):,} CAD points to the reference…', flush=True)
    model_distance, model_closest = _nearest(reference_target, model_points)
    # A supplementary volume estimate integrates only the removed surface
    # patches against their replacement planes. The reference
    # has mesh defects, so this is evidence rather than an acceptance criterion.
    centers = reference.triangles_center
    correction = 0.
    for name, (low, high) in DECORATION_BOXES.items():
        selected = ((centers >= low) & (centers <= high)).all(axis=1)
        axis = 1 if name == 'back_brand_and_three_ovals' else 2
        coordinate = -4.96942 if 'groove_dovetail' in name else 0.
        correction -= float(np.sum((centers[selected, axis]-coordinate) * reference.face_normals[selected, axis] * reference.area_faces[selected]))
    print('Checking the restored flat surfaces…', flush=True)
    mating_regions = {}
    for direction, points, distances, closest in [
        ('reference_to_model', source_points, source_distance, source_closest),
        ('model_to_reference', model_points, model_distance, model_closest),
    ]:
        for name, mask in mating_region_masks(points).items():
            if not np.any(mask):
                raise ValueError(f'No comparison samples in mechanical region {name}')
            mating_regions.setdefault(name, {})[direction] = _summary(
                points[mask], distances[mask], closest[mask], mating_tolerance)
    mating_passed = all(
        row['max_mm'] <= mating_tolerance
        for directions in mating_regions.values() for row in directions.values()
    )
    result = {
        'source': str(SOURCE),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'model_sha256': hashlib.sha256(model_path.read_bytes()).hexdigest(),
        'method': 'Exact Euclidean point-to-triangle distances; deterministic area samples plus vertices, both directions. This is a sampled comparison, not a Hausdorff proof.',
        'tolerance_mm': tolerance,
        'mating_tolerance_mm': mating_tolerance,
        'mating_regions': mating_regions,
        'mating_regions_within_sampled_tolerance': mating_passed,
        'decoration_exclusion_boxes_mm': DECORATION_BOXES,
        'excluded_points': {'reference': int(source_mask.sum()), 'model': int(model_mask.sum())},
        'source_bounds_mm': reference.bounds.tolist(),
        'model_bounds_mm': model.bounds.tolist(),
        'source_watertight': bool(reference.is_watertight),
        'model_watertight': bool(model.is_watertight),
        'model_winding_consistent': bool(model.is_winding_consistent),
        'model_volume_mm3': float(model.volume),
        'estimated_cleaned_reference_volume_mm3': float(reference.volume + correction),
        'cosmetic_cleanup': _cosmetic_cleanup(target),
        'reference_to_model': _summary(source_points, source_distance, source_closest, tolerance),
        'model_to_reference': _summary(model_points, model_distance, model_closest, tolerance),
    }
    result['within_sampled_tolerance'] = bool(
        model.is_watertight and model.is_winding_consistent
        and source_distance.max() <= tolerance and model_distance.max() <= tolerance
        and result['cosmetic_cleanup']['passed']
        and mating_passed
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    np.savez_compressed(output.with_suffix('.npz'),
        reference_points=source_points, reference_distances=source_distance,
        model_points=model_points, model_distances=model_distance)
    return result
