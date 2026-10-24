"""Audit every supported native rail against the complete supplied STL surface.

Run after sourcing .local-env. The analytic CAD builders never import a source
mesh; this separate measurement tool records the evidence for each family.
"""
from dataclasses import asdict
import hashlib
import json

import trimesh

from vault.geared_rails import GearRailSpec, build_gear_rail, rail_dimensions
from vault.reference import PROJECT_ROOT
from vault.tessellation import _tessellate
from vault.validation import _distance_target, _nearest, _surface_points


def main():
    output = PROJECT_ROOT / 'out/reviews/geared-rail-families'
    output.mkdir(parents=True, exist_ok=True)
    report = {
        'schema': 'vault-geared-rail-families-reference/v1',
        'units': 'mm',
        'method': 'Bidirectional exact point-to-triangle distances on 20000 deterministic '
                  'area samples plus all source and model vertices; 0.0025 mm native chord '
                  'tolerance. No surfaces excluded.',
        'distance_limit_mm': .1,
        'construction_sha256': hashlib.sha256(
            (PROJECT_ROOT / 'src/vault/geared_rails.py').read_bytes()).hexdigest(),
        'parts': [],
    }
    for family in ('S', 'M', 'L'):
        source_path = PROJECT_ROOT / f'original_files/01. DRAWERS/07. Universal/Geared Rails/{family} Rails.stl'
        source = trimesh.load_mesh(source_path)
        components = sorted(source.split(), key=lambda mesh: mesh.bounds[0, 1])
        for retained, original in zip((True, False), components, strict=True):
            # Register using the unfeatured straight back edge. The retained
            # mesh extends 1.4187 mm behind that datum through its native rib.
            origin = original.bounds[0].copy()
            if retained:
                origin[1] += 1.4187
            original.vertices -= origin
            native = build_gear_rail(retained, spec=GearRailSpec(family))
            mesh = _tessellate(native, output / f'{family.lower()}_{retained}.stl',
                               deflection=.0025)
            forward, _ = _nearest(_distance_target(mesh),
                                   _surface_points(original, 20_000, seed=1001))
            reverse, _ = _nearest(_distance_target(original),
                                   _surface_points(mesh, 20_000, seed=2002))
            item = {
                'family': family, 'retained': retained,
                'source': str(source_path.relative_to(PROJECT_ROOT)),
                'source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
                'source_subtract_origin_mm': origin.tolist(),
                'dimensions': asdict(rail_dimensions(family)),
                'source_volume_mm3': float(original.volume),
                'native_volume_mm3': float(native.volume),
                'source_to_native_max_mm': float(forward.max()),
                'native_to_source_max_mm': float(reverse.max()),
                'passed': bool(forward.max() < .1 and reverse.max() < .1),
            }
            report['parts'].append(item)
            print(f'{family} {"retained" if retained else "plain"}: '
                  f'{max(forward.max(), reverse.max()):.5f} mm maximum sampled deviation', flush=True)
    report['passed'] = all(part['passed'] for part in report['parts'])
    destination = PROJECT_ROOT / 'research/geared_rail_families_reference.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'report': str(destination)}), flush=True)
    if not report['passed']:
        raise SystemExit('Geared rail family reference audit failed')


if __name__ == '__main__':
    main()
