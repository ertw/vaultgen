"""Reproducible sampled comparison of S4 box against its purchased source.

Reports all surfaces, including simplified blends and branding.
This reports measured deviations; it does not assert mechanical equivalence.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import trimesh
from vault.reference import PROJECT_ROOT
from vault.tessellation import load_model
from vault.validation import _surface_points, _distance_target, _nearest, _summary


def main():
    source = PROJECT_ROOT / 'original_files/01. DRAWERS/01. S Families/S4/Boxes/S4 Box 1F.stl'
    build = (PROJECT_ROOT / 'out/latest/s4_box_1f').resolve()
    path = build / 's4_box_1f.step'
    reference = trimesh.load_mesh(source)
    origin = [9001.5546875, 1167.24138, 1.0]
    reference.vertices = reference.vertices[:, [0, 1, 2]] - origin
    model = load_model(path)
    report = {
        'source': str(source.relative_to(PROJECT_ROOT)),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'model': str(path.relative_to(PROJECT_ROOT)),
        'model_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'registration': {'axis_order': [0, 1, 2], 'subtract_origin_mm': origin},
        'method': 'Deterministic 20000 area samples plus up to 20000 vertices, exact point-to-triangle distance, bidirectional; no exclusions.',
        'known_changes': ['Branding omitted',
                          'Simplified runner blends and regularly spaced breakaway support teeth',
                          'Nominal rear support panel with two flared roof contacts',
                          'Rectangular attachment recesses and simplified front lands'],
        'source_watertight': bool(reference.is_watertight),
    }
    for name, a, b in [('reference_to_model', reference, model), ('model_to_reference', model, reference)]:
        points = _surface_points(a, 20000, 12345)
        distances, closest = _nearest(_distance_target(b), points)
        report[name] = _summary(points, distances, closest, .25)
        print(name, {k: report[name][k] for k in ['p95_mm', 'p99_mm', 'max_mm']}, flush=True)
    (PROJECT_ROOT / 'research/box_comparison.json').write_text(json.dumps(report, indent=2) + '\n')

if __name__ == '__main__':
    main()
