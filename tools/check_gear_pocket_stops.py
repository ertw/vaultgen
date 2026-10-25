"""Measure blind rail-pocket ends in the purchased S4/M3/L6 box meshes.

Rays run from the central lock opening toward each blind end, at the
assembled rail nose's center height and thickness. Only triangles crossing
the ray's Y/Z coordinates are retained for the intersection; no mesh repair
or source mutation is performed. Source end blends differ from the native
flat stop, so this establishes the stop's location, not full equivalence.
"""
import hashlib
import json

import numpy as np
import trimesh

from vault.reference import PROJECT_ROOT


def main():
    records = []
    for family, depth, height in [('S', 4, 1), ('M', 3, 1), ('L', 6, 2)]:
        path = next((PROJECT_ROOT / 'original_files').rglob(
            f'{family}{depth} Box {height}F.stl'))
        mesh = trimesh.load_mesh(path)
        origin = np.array([mesh.bounds[:, 0].mean(),
                           mesh.bounds[0, 1] - 2.3, mesh.bounds[0, 2] - 5])
        mesh.vertices -= origin
        triangles = mesh.triangles
        lower, upper = triangles.min(axis=1), triangles.max(axis=1)
        ends = []
        for z, sign in [(9.207, 1), (37.793, -1)]:
            y = 42 * depth + 20.1 - 3.1
            mask = ((lower[:, 1] <= y) & (upper[:, 1] >= y)
                    & (lower[:, 2] <= z) & (upper[:, 2] >= z))
            section = trimesh.Trimesh(vertices=mesh.vertices,
                                     faces=mesh.faces[mask], process=False)
            hits, _, _ = section.ray.intersects_location(
                [[sign * 23, y, z]], [[sign, 0, 0]], multiple_hits=True)
            positions = sorted((sign * hits[:, 0]).tolist())
            assert len(positions) >= 2, positions
            ends.append({'rail': 'lower_plain' if sign == 1 else 'upper_retained',
                         'ray_origin_mm': [sign * 23, y, z],
                         'ray_direction': [sign, 0, 0],
                         'blind_end_x_mm': sign * positions[0],
                         'outer_wall_x_mm': sign * positions[-1]})
        records.append({'family': family, 'depth_units': depth, 'height_units': height,
                        'source': str(path.relative_to(PROJECT_ROOT)),
                        'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'subtract_origin_mm': origin.tolist(), 'ends': ends})
        print(json.dumps(records[-1]), flush=True)
    report = {
        'schema': 'vault-gear-pocket-stops/v1', 'units': 'mm',
        'method': __doc__.strip(), 'sources': records,
        'native_stop_x_mm': [-66.3, 66.3],
        'decision': 'Preserve the user-confirmed working native S4/S-rail stop datum '
                    'for all families. Original S/M/L pockets also end near the '
                    'central mechanism; their local rounded ends differ. M/L rail '
                    'extensions belong only to the outgoing tail.',
        'regression': 'tests.test_gear_fit.UnlockedRailStopTests checks both rails '
                      'in S/M/L 1F and 2F: contact without overlap at the stop, '
                      'blocked inward overtravel, and clear 0/10/20 mm operation.',
    }
    destination = PROJECT_ROOT / 'research/gear_pocket_stops.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
