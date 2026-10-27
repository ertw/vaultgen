"""Measure L² references and compare retained runner/divider sections with CAD.

Run after sourcing .local-env. Purchased triangles are diagnostic inputs only.
The comparison samples exact source plane intersections and finely sampled
native CAD section edges. It is a local interface audit, not a full-surface
equivalence or physical printed-fit test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from build123d import Plane
from shapely import distance, points
from shapely.geometry import MultiLineString

from vault.model import build_module
from vault.reference import PROJECT_ROOT
from vault.spec import ModuleSpec


CASES = {'l3-1f': (3, 1), 'l6-2f': (6, 2)}
ROTATION = np.array([[-2**-.5, -2**-.5, 0],
                     [0, 0, 1], [-2**-.5, 2**-.5, 0]])


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_triangles(spec):
    """Register the supplied 45-degree export with a proper rigid rotation."""
    name = f'L{spec.depth_units}² Module {spec.height_units}F.stl'
    path = next((PROJECT_ROOT / 'original_files/01. DRAWERS').rglob(name))
    dtype = np.dtype([('normal', '<f4', 3), ('vertices', '<f4', (3, 3)),
                      ('attribute', '<u2')])
    with path.open('rb') as stream:
        stream.seek(80)
        triangle_count = int.from_bytes(stream.read(4), 'little')
    if path.stat().st_size != 84 + triangle_count * dtype.itemsize:
        raise ValueError(f'Expected a binary STL: {path}')
    records = np.memmap(path, dtype=dtype, mode='r', offset=84,
                        shape=(triangle_count,))
    triangles = records['vertices'].astype(float) @ ROTATION.T
    vertices = triangles.reshape(-1, 3)
    bounds = np.array([vertices.min(axis=0), vertices.max(axis=0)])
    # Upper stacking-connector datum is +4.8009 mm above the top skin.
    # The datum is shared with the established S-module registration.
    origin = np.array([bounds[:, 0].mean(), bounds[0, 1],
                       bounds[1, 2] - spec.height - 4.8009])
    triangles -= origin
    return triangles, {
        'source': str(path.relative_to(PROJECT_ROOT)),
        'source_sha256': sha256(path),
        'registration': {'rotation_matrix': ROTATION.tolist(),
                         'rotation_determinant': float(np.linalg.det(ROTATION)),
                         'subtract_after_rotation_mm': origin.tolist(),
                         'formula': 'native = original @ rotation.T - origin'},
        'source_bounds_mm': (bounds-origin).tolist(),
    }


def source_section(triangles, axis, offset):
    """Intersect triangles directly, avoiding mesh repair or vertex movement."""
    signed = triangles[:, :, axis] - offset
    selected = (signed.min(axis=1) < 0) & (signed.max(axis=1) > 0)
    triangles, signed = triangles[selected], signed[selected]
    pieces = []
    for i, j, k in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        crossing = (signed[:, i]*signed[:, j] < 0) & (signed[:, i]*signed[:, k] < 0)
        tri, delta = triangles[crossing], signed[crossing]
        if not len(tri):
            continue
        endpoints = [tri[:, i] + (tri[:, target]-tri[:, i]) *
                     (-delta[:, i]/(delta[:, target]-delta[:, i]))[:, None]
                     for target in (j, k)]
        pieces.append(np.stack(endpoints, axis=1))
    return np.concatenate(pieces)


def crossings(segments, axis, value, result_axis):
    low, high = segments[:, 0, axis], segments[:, 1, axis]
    selected = (low-value)*(high-value) < 0
    segment, low, high = segments[selected], low[selected], high[selected]
    result = segment[:, 0, result_axis] + (segment[:, 1, result_axis] -
             segment[:, 0, result_axis]) * (value-low)/(high-low)
    return np.unique(np.round(result, 5)).tolist()


def native_section(shape, y):
    segments = []
    for face in shape.intersect(Plane(origin=(0, y, 0), z_dir=(0, 1, 0))):
        for edge in face.edges():
            count = max(2, int(np.ceil(edge.length/.04))+1)
            samples = np.array([[p.X, p.Z] for p in
                               (edge.position_at(t) for t in np.linspace(0, 1, count))])
            segments.extend(np.stack((samples[:-1], samples[1:]), axis=1))
    return np.asarray(segments)


def interface_mask(samples, spec, *, tunnel_only=False, include_mouths=False):
    """Retain four runner interfaces and the central stopper-access tunnel."""
    x, z = samples.T
    selected = np.zeros(len(samples), dtype=bool)
    floor, ceiling = (6, 41) if include_mouths else (9.4, 37.6)
    for tier in spec.tier_offsets:
        if not tunnel_only:
            for center in spec.drawer_centers:
                side = abs(x-center)
                selected |= ((side >= 67.2) & (side <= 79.6) &
                             (z >= tier+floor) & (z <= tier+ceiling))
        selected |= ((abs(x) <= (2.21 if tunnel_only else 3.1)) &
                     (z >= tier+16) & (z <= tier+31))
    return selected


def sampled_distances(segments, target, spec, *, tunnel_only=False, include_mouths=False):
    samples = np.concatenate([segments[:, 0], segments[:, 1], segments.mean(axis=1)])
    samples = samples[interface_mask(samples, spec, tunnel_only=tunnel_only,
                                     include_mouths=include_mouths)]
    values = np.asarray(distance(points(samples), MultiLineString(target.tolist())))
    return {'sample_count': len(samples), 'maximum_mm': float(values.max()),
            'p99_mm': float(np.quantile(values, .99)),
            'worst_point_xz_mm': samples[values.argmax()].tolist()}


def check_case(name):
    depth, height = CASES[name]
    spec = ModuleSpec('L', depth, height, drawer_columns=2)
    triangles, record = source_triangles(spec)
    record.update({'case': name, 'depth_units': depth, 'height_units': height,
                   'drawer_family': 'S', 'drawer_centers_mm': list(spec.drawer_centers)})
    middle = source_section(triangles, 1, 50)
    record['source_datums'] = {
        'center_divider_crossings_x_at_y50_z23_5_mm':
            [x for x in crossings(middle, 2, 23.5, 0) if abs(x)<20],
        'cavity_crossings_x_at_y50_z40_mm': crossings(middle, 2, 40, 0),
        'central_tunnel_crossings_z_at_y50_x0_mm': crossings(middle, 0, 0, 2),
        'nominal_tunnel': {'width_mm': 4.4, 'height_mm': 6.32,
                           'center_z_mm': [23.5+t for t in spec.tier_offsets],
                           'rear_entry_radius_mm': 3.0},
    }
    longitudinal = source_section(triangles, 0, 0)
    record['source_datums']['tunnel_rear_flare_z_mm'] = {
        str(y): [z for z in crossings(longitudinal, 1, y, 2) if 16<z<31]
        for y in (.1, 1., 2., 3.1)}
    record['source_datums']['tunnel_end_y_mm'] = crossings(longitudinal, 2, 23.5, 1)
    shape = build_module(spec=spec, include_supports=False)
    record['native'] = {'valid': bool(shape.is_valid), 'solid_count': len(shape.solids()),
                        'shell_count': len(shape.shells()), 'volume_mm3': shape.volume}
    record['sections'] = []
    # y=1 checks the access-tunnel entry; runner starts differ intentionally
    # with the 0.9 mm native back, so only the tunnel is checked separately.
    for y in (1., 50., spec.depth/2+28.50005, spec.depth-3.1):
        source = source_section(triangles, 1, y)[:, :, [0, 2]]
        native = native_section(shape, y)
        forward = sampled_distances(source, native, spec, tunnel_only=y == 1.,
                                     include_mouths=y > spec.depth-6)
        reverse = sampled_distances(native, source, spec, tunnel_only=y == 1.,
                                     include_mouths=y > spec.depth-6)
        result = {'y_mm': y, 'region': 'access tunnel only' if y == 1. else 'runners and divider',
                  'source_to_native': forward, 'native_to_source': reverse,
                  'passed': max(forward['maximum_mm'], reverse['maximum_mm']) <= .1}
        record['sections'].append(result)
        print(f'{name}, Y={y:.3f}: maximum '
              f'{max(forward["maximum_mm"], reverse["maximum_mm"]):.5f} mm', flush=True)
    record['passed'] = all(s['passed'] for s in record['sections'])
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', choices=CASES)
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT/'research/multi_drawer.json')
    args = parser.parse_args()
    construction_files = ['model.py', 'spec.py', 'shell.py', 'envelope.py',
                          'connectors.py', 'shadow_gap.py']
    report = {
        'schema': 'vault-multi-drawer-reference/v1', 'units': 'mm',
        'method': __doc__.strip(), 'interface_distance_limit_mm': .1,
        'native_section_edge_step_mm': .04,
        'construction_sha256': {name: sha256(PROJECT_ROOT/'src/vault'/name)
                                for name in construction_files},
        'reference_inventory': {'L²': {'depths': list(range(3, 8)), 'heights': [1, 2, 4]},
                                'XL²': {'depths': list(range(3, 8)), 'heights': [1],
                                        'layout': 'S + M; excluded from generator'}},
        'limitations': 'Samples four runner/mouth interfaces and the center-divider '
                       'stopper access at four transverse planes, including one dedicated '
                       'to the rear tunnel entry. Native removable '
                       'mouth supports are removed for this finished-interface audit. '
                       'The different rear thickness, mounting bores, outer styling, branding, stacking '
                       'connectors and front shadow rebate are not compared. The audit '
                       'does not establish whole-surface equivalence, accessory insertion '
                       'or physical printed fit.',
        'cases': [check_case(name) for name in (args.case or CASES)],
    }
    report['passed'] = all(case['passed'] for case in report['cases'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f'Wrote {args.output}; passed={report["passed"]}', flush=True)
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
