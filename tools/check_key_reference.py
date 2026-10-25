"""Audit the reconstructed key exterior against the complete purchased STL.

Source the local runtime before running this tool. The native comparison is
the fused gear and handle blanks, before any intentional snap-joint cuts.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh

from vault.key_geometry import D, SOURCE_ORIGIN, build_gear_blank, build_handle_blank
from vault.reference import PROJECT_ROOT
from vault.tessellation import _tessellate
from vault.validation import _distance_target, _nearest, _surface_points, _summary


SOURCE = PROJECT_ROOT / 'original_files/01. DRAWERS/07. Universal/Key (Turn On Supports).stl'
CONSTRUCTION = PROJECT_ROOT / 'src/vault/key_geometry.py'
MECHANICAL_TOLERANCE = .1
# Include 1 µm of numerical slack around the measured Z=1 mm recess ceiling.
BRANDING_BOX = [[-10., -4., -.001], [10., 4., 1.001]]


def _branding_mask(points):
    return ((points >= BRANDING_BOX[0]) & (points <= BRANDING_BOX[1])).all(axis=1)


def _region_masks(points):
    z = points[:, 2]
    return {
        'gear_and_oval_wing_z0_to_7_4': (z >= -.001) & (z <= 7.401),
        'locating_flange_and_neck_z7_4_to_18_4': (z >= 7.399) & (z <= 18.401),
        'grip_above_z18_4': z > 18.401,
    }


def _diagnostic_masks(points):
    z = points[:, 2]
    radius = np.linalg.norm(points[:, :2], axis=1)
    return {
        'gear_flanks_z3_3_to_6_35': (z >= 3.3) & (z <= 6.35),
        'locating_flange_z8_3_to_10_7': (z >= 8.3) & (z <= 10.7),
        'indexing_tabs_z10_9_to_14_4_radius_above_17_2':
            (z >= 10.9) & (z <= 14.4) & (radius > 17.2),
        'rounded_rim_z15_8_to_17_2_radius_above_16_9':
            (z >= 15.8) & (z <= 17.2) & (radius > 16.9),
    }


def _targeted_extrema(mesh):
    """Keep small known rim seams from disappearing between random samples."""
    vertices = np.asarray(mesh.vertices)
    indices = []
    for mask in _diagnostic_masks(vertices).values():
        selected = np.flatnonzero(mask)
        if not len(selected):
            continue
        points = vertices[selected]
        for axis in range(3):
            indices.extend((selected[np.argmin(points[:, axis])],
                            selected[np.argmax(points[:, axis])]))
        radius = np.linalg.norm(points[:, :2], axis=1)
        indices.extend((selected[np.argmin(radius)], selected[np.argmax(radius)]))
    return vertices[np.unique(indices)]


def _summarize_selected(points, distances, closest, mask):
    if not np.any(mask):
        raise ValueError('Reference audit has no samples in a required region')
    return _summary(points[mask], distances[mask], closest[mask], MECHANICAL_TOLERANCE)


def _plot_distances(results, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    largest = max(float(row[2].max()) for row in results)
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), layout='constrained')
    for row, (label, points, distances, _) in enumerate(results):
        order = np.argsort(distances)
        for column, (x, y) in enumerate(((0, 1), (0, 2), (1, 2))):
            ax = axes[row, column]
            dots = ax.scatter(points[order, x], points[order, y],
                              c=np.maximum(distances[order], .0001), s=1.,
                              cmap='turbo', norm=LogNorm(vmin=.001, vmax=max(.1, largest)),
                              rasterized=True)
            ax.set(xlabel=f'{"XYZ"[x]} (mm)', ylabel=f'{"XYZ"[y]} (mm)',
                   title=f'{label.replace("_", " ")}: {"XYZ"[x]} / {"XYZ"[y]}')
            ax.set_aspect('equal')
        fig.colorbar(dots, ax=axes[row, :], label='Surface deviation (mm)', shrink=.8)
    fig.suptitle('Key exterior — all sampled surfaces, including omitted underside branding')
    fig.savefig(path, dpi=150)
    plt.close(fig)


def compare(*, samples=10_000, report_path=None, review_dir=None):
    if samples <= 0:
        raise ValueError('Sample count must be positive')
    report_path = Path(report_path or PROJECT_ROOT / 'research/key_reference.json')
    review_dir = Path(review_dir or PROJECT_ROOT / 'out/reviews/key-reference')
    construction_hash = hashlib.sha256(CONSTRUCTION.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    print('Loading the original key and constructing the native unsplit blank…', flush=True)
    source = trimesh.load_mesh(SOURCE)
    source.vertices -= np.asarray(SOURCE_ORIGIN)
    blank = build_gear_blank().fuse(build_handle_blank())
    if isinstance(blank, list):
        if len(blank) != 1:
            raise ValueError('Native key exterior must be connected')
        blank = blank[0]
    if not blank.is_valid or len(blank.solids()) != 1 or len(blank.shells()) != 1:
        raise ValueError('Native key exterior must be one valid solid with one boundary shell')
    review_dir.mkdir(parents=True, exist_ok=True)
    model = _tessellate(blank, review_dir / 'native-unsplit-blank.stl', deflection=.0025)
    source_extrema, model_extrema = _targeted_extrema(source), _targeted_extrema(model)
    source_points = np.vstack((_surface_points(source, samples, seed=73101), source_extrema))
    model_points = np.vstack((_surface_points(model, samples, seed=73102), model_extrema))
    print('Preparing spatial indices without changing either triangle surface…', flush=True)
    model_target = _distance_target(model)
    source_target = _distance_target(source)
    print(f'Comparing {len(source_points):,} original points to native CAD…', flush=True)
    source_distances, source_closest = _nearest(model_target, source_points)
    print(f'Comparing {len(model_points):,} native points to the original…', flush=True)
    model_distances, model_closest = _nearest(source_target, model_points)
    results = [
        ('reference_to_native', source_points, source_distances, source_closest),
        ('native_to_reference', model_points, model_distances, model_closest),
    ]
    regions, mechanical, decoration, whole, diagnostics = {}, {}, {}, {}, {}
    for direction, points, distances, closest in results:
        whole[direction] = _summary(points, distances, closest, MECHANICAL_TOLERANCE)
        branding = _branding_mask(points)
        decoration[direction] = _summarize_selected(points, distances, closest, branding)
        for name, mask in _diagnostic_masks(points).items():
            diagnostics.setdefault(name, {})[direction] = _summarize_selected(
                points, distances, closest, mask)
        for name, mask in _region_masks(points).items():
            regions.setdefault(name, {})[direction] = _summarize_selected(
                points, distances, closest, mask)
            if name != 'grip_above_z18_4':
                mechanical.setdefault(name, {})[direction] = _summarize_selected(
                    points, distances, closest, mask & ~branding)
    mechanical_passed = all(row['max_mm'] <= MECHANICAL_TOLERANCE
                            for directions in mechanical.values() for row in directions.values())
    whole_passed = all(row['max_mm'] <= MECHANICAL_TOLERANCE for row in whole.values())
    report = {
        'schema': 'vault-key-reference-audit/v1',
        'units': 'mm',
        'source': str(SOURCE.relative_to(PROJECT_ROOT)),
        'source_sha256': source_hash,
        'construction_sha256': construction_hash,
        'dimensions': asdict(D),
        'source_subtract_origin_mm': list(SOURCE_ORIGIN),
        'method': 'Bidirectional exact point-to-triangle distances using a spatial index; '
                  'deterministic area-weighted samples plus vertices and targeted XYZ/radial '
                  'extrema in named diagnostic regions. Target triangles are '
                  'subdivided to tighten bounding boxes without changing their surfaces.',
        'area_samples_per_direction': samples,
        'maximum_vertices_added_per_direction': samples,
        'additional_targeted_extrema_points': {
            'reference': len(source_extrema), 'native': len(model_extrema),
        },
        'native_tessellation_absolute_chord_tolerance_mm': .0025,
        'mechanical_tolerance_mm': MECHANICAL_TOLERANCE,
        'source_bounds_mm': source.bounds.tolist(),
        'native_bounds_mm': model.bounds.tolist(),
        'source_watertight': bool(source.is_watertight),
        'native_watertight': bool(model.is_watertight),
        'native_winding_consistent': bool(model.is_winding_consistent),
        'source_volume_mm3': float(source.volume),
        'native_volume_mm3': float(blank.volume),
        'whole_exterior': whole,
        'whole_exterior_within_sampled_tolerance': whole_passed,
        'raw_regions_including_decoration': regions,
        'retained_mechanical_regions': mechanical,
        'mechanical_regions_within_sampled_tolerance': mechanical_passed,
        'diagnostic_subregions': diagnostics,
        'diagnostic_subregions_note': 'These narrower bands describe the gear flanks, '
                                     'locating flange, indexing tabs and rounded rim. '
                                     'They do not replace strict whole-region acceptance.',
        'omitted_underside_branding': {
            'exclusion_box_mm': BRANDING_BOX,
            'description': 'Recessed lettering on the underside is intentionally replaced by '
                           'the original bottom plane. Only this central underside box is '
                           'excluded from retained mechanical acceptance; its distances remain '
                           'in the whole-exterior and raw gear-region measurements.',
            'distances': decoration,
        },
        'regularization': {
            'mechanical': 'Native arcs, planes and ruled transitions replace triangulated '
                          'source surfaces. Mechanical acceptance remains 0.1 mm with no '
                          'tolerance exception for regularization.',
            'grip': 'The long capsule foot blend is regularized to a smooth native surface. '
                    'Differences above Z=18.4 are reported separately and are not treated '
                    'as gear, locating-flange or neck fit acceptance.',
            'snap_joint': 'Both native blanks are fused before comparison. New sockets, '
                          'spring slots and retention features are absent from this exterior audit.',
        },
        'acceptance': 'Passed means the native blank is valid and every sampled point in '
                      'both retained mechanical regions is within 0.1 mm in both directions. '
                      'It does not assert full exterior equality, grip equivalence or physical fit.',
        'limitations': 'A sampled comparison, not a proven Hausdorff bound. Source volume '
                      'is descriptive only. This audit does not test snap deflection, assembly '
                      'force, torque capacity, printer accuracy or a physical print.',
        'passed': bool(mechanical_passed and model.is_watertight and model.is_winding_consistent),
    }
    if (hashlib.sha256(CONSTRUCTION.read_bytes()).hexdigest() != construction_hash
            or hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_hash):
        raise RuntimeError('Key geometry or reference changed during comparison; rerun with stable inputs')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    np.savez_compressed(review_dir / 'surface-deviations.npz',
                        reference_points=source_points, reference_distances=source_distances,
                        reference_nearest=source_closest,
                        native_points=model_points, native_distances=model_distances,
                        native_nearest=model_closest)
    _plot_distances(results, review_dir / 'surface-deviations.png')
    from vault.render import render_mesh
    render_mesh(source, review_dir / 'reference-isometric.png')
    render_mesh(model, review_dir / 'native-isometric.png')
    for name, directions in mechanical.items():
        print(name, {direction: row['max_mm'] for direction, row in directions.items()}, flush=True)
    print(json.dumps({'passed': report['passed'],
                      'whole_exterior_within_sampled_tolerance': whole_passed,
                      'report': str(report_path)}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=10_000,
                        help='area-weighted samples per direction, plus up to this many vertices')
    parser.add_argument('--report', type=Path, default=PROJECT_ROOT / 'research/key_reference.json')
    parser.add_argument('--review-dir', type=Path, default=PROJECT_ROOT / 'out/reviews/key-reference')
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error('--samples must be positive')
    report = compare(samples=args.samples, report_path=args.report, review_dir=args.review_dir)
    if not report['passed']:
        raise SystemExit('Key retained mechanical reference audit failed; see reported distances')


if __name__ == '__main__':
    main()
