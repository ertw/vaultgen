"""Compare every native x3..x7 slide to both purchased layout copies.

This read-only reference audit ignores disconnected zero-volume STL debris.
No source geometry is required by the constructor. Temporary tessellations
are removed automatically so checking the family does not retain large files.
"""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import trimesh

from vault.reference import PROJECT_ROOT
from vault.runner_slides import RunnerSlideSpec, build_runner_slide
from vault.tessellation import _tessellate
from vault.validation import _distance_target, _nearest, _surface_points


def main():
    report = {
        'schema': 'vault-runner-slides-reference/v1', 'units': 'mm',
        'method': 'Bidirectional point-to-triangle distances on 5000 deterministic '
                  'area samples plus up to 5000 sampled vertices per direction, '
                  'native chord tolerance .0025 mm. '
                  'Each source component is centered in X and translated to Y=Z=0. '
                  'Only disconnected zero-volume source triangles are excluded.',
        'distance_limit_mm': .08,
        'construction_sha256': hashlib.sha256(
            (PROJECT_ROOT / 'src/vault/runner_slides.py').read_bytes()).hexdigest(),
        'source_pair': 'Two geometrically identical pieces, within binary-STL quantization.',
        'parts': [],
    }
    with TemporaryDirectory(prefix='vault-slide-audit-') as folder:
        for depth in range(3, 8):
            path = PROJECT_ROOT / f'original_files/01. DRAWERS/07. Universal/Runners/x{depth} Runner Slides.stl'
            original = trimesh.load_mesh(path)
            components = sorted([p for p in original.split(only_watertight=False)
                                 if p.volume > 100], key=lambda p: p.bounds[0, 0])
            assert len(components) == 2
            native = build_runner_slide(spec=RunnerSlideSpec(depth))
            mesh = _tessellate(native, Path(folder) / 'slide.stl', deflection=.0025)
            native_target = _distance_target(mesh)
            for side, source in zip(('left', 'right'), components):
                origin = source.bounds[0].copy()
                origin[0] = source.bounds[:, 0].mean()
                source.vertices -= origin
                forward, _ = _nearest(native_target, _surface_points(source, 5000, seed=101))
                reverse, _ = _nearest(_distance_target(source), _surface_points(mesh, 5000, seed=202))
                item = {
                    'depth_units': depth, 'side': side,
                    'source': str(path.relative_to(PROJECT_ROOT)),
                    'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'source_subtract_origin_mm': origin.tolist(),
                    'source_bounds_mm': source.bounds.tolist(),
                    'source_volume_mm3': float(source.volume),
                    'native_volume_mm3': float(native.volume),
                    'relative_volume_difference': abs(float(native.volume / source.volume - 1)),
                    'source_to_native_max_mm': float(forward.max()),
                    'native_to_source_max_mm': float(reverse.max()),
                    'passed': bool(max(forward.max(), reverse.max()) < .08
                                   and abs(native.volume/source.volume-1) < .001),
                }
                report['parts'].append(item)
                print(f'x{depth} {side}: {max(forward.max(), reverse.max()):.5f} mm max deviation; '
                      f'{item["relative_volume_difference"]:.5%} volume difference', flush=True)
    report['passed'] = all(p['passed'] for p in report['parts'])
    report['limitations'] = 'Digital source reconstruction only; printer and material fit remain unqualified.'
    destination = PROJECT_ROOT / 'research/runner_slides_reference.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    if not report['passed']:
        raise SystemExit('Runner slide reference audit failed')


if __name__ == '__main__':
    main()
