"""Reproducible sampled comparison of S1F facade against its purchased source.

Reports all surfaces, including the intentional rebate and simplified branding.
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
    source = PROJECT_ROOT / 'original_files/01. DRAWERS/01. S Families/Facades/S1F (Turn On Supports).stl'
    build = (PROJECT_ROOT / 'out/latest/s1f_facade').resolve()
    path = build / 's1f_facade.step'
    reference = trimesh.load_mesh(source)
    origin = [9001.55517578, 138.33726501, 1908.10327148]
    reference.vertices = reference.vertices[:, [0, 2, 1]] - origin
    reference.faces = reference.faces[:, ::-1]
    model = load_model(path)
    report = {
        'source': str(source.relative_to(PROJECT_ROOT)),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'model': str(path.relative_to(PROJECT_ROOT)),
        'model_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'registration': {'axis_order': [0, 2, 1], 'subtract_origin_mm': origin},
        'method': 'Deterministic 20000 area samples plus up to 20000 vertices, exact point-to-triangle distance, bidirectional; no exclusions.',
        'known_changes': ['0.5 mm deep by 1 mm wide rear perimeter rebate',
                          'Small molded branding and front indexing marks omitted',
                          'Native curve approximation of rolled outside, pocket blends and handle lip'],
        'source_watertight': bool(reference.is_watertight),
    }
    for name, a, b in [('reference_to_model', reference, model), ('model_to_reference', model, reference)]:
        points = _surface_points(a, 20000, 12345)
        distances, closest = _nearest(_distance_target(b), points)
        report[name] = _summary(points, distances, closest, .25)
        print(name, {k: report[name][k] for k in ['p95_mm', 'p99_mm', 'max_mm']}, flush=True)
    (PROJECT_ROOT / 'research/facade_comparison.json').write_text(json.dumps(report, indent=2) + '\n')

if __name__ == '__main__':
    main()
