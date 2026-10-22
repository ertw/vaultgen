"""Build, export, render, and measure the reconstruction."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from .reference import PROJECT_ROOT
from .spec import DEFAULT_SPEC, FAMILIES, ModuleSpec
from ._build import Build, set_latest, source_hashes, verify_files, write_json


def _build_into(output: Path, spec: ModuleSpec = DEFAULT_SPEC):
    from .model import build_module

    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    print('Building native shell and mechanical connectors…', flush=True)
    module = build_module(spec=spec, progress=lambda message: print(message, flush=True))
    return _export_into(module, output, started, spec)


def _export_into(module, output: Path, started: float, spec: ModuleSpec = DEFAULT_SPEC):
    """Export and check an already constructed native model."""
    from build123d import export_brep, export_step
    from .render import render_review
    import trimesh
    from dataclasses import asdict

    output.mkdir(parents=True, exist_ok=True)
    stem = spec.slug
    print('Exporting STEP, BREP, and STL…', flush=True)
    export_step(module, output / f'{stem}.step')
    export_brep(module, output / f'{stem}.brep')
    # Model-space mesh is retained explicitly for reproducible surface checks.
    # build123d 0.13's STL helper uses relative deflection. Use an absolute
    # 0.05 mm edge chord tolerance, suitable for these printable features.
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.StlAPI import StlAPI_Writer
    BRepTools.Clean_s(module.wrapped)
    mesher = BRepMesh_IncrementalMesh()
    mesher.SetShape(module.wrapped)
    settings = mesher.ChangeParameters()
    settings.Deflection = .05
    settings.Angle = .5
    settings.Relative = False
    settings.InParallel = True
    # Retain interior deflection control: trimming a curved face can otherwise
    # leave long triangles whose interiors miss the native surface badly.
    settings.ControlSurfaceDeflection = True
    mesher.Perform()
    if not mesher.IsDone():
        raise ValueError('Absolute-tolerance CAD tessellation failed')
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(module.wrapped, str(output / f'{stem}_model.stl')):
        raise ValueError('STL export failed')
    mesh = trimesh.load_mesh(output / f'{stem}_model.stl')
    faces_before = len(mesh.faces)
    # OCC can emit repeated or collapsed triangles on very short trimmed edges.
    # Remove only exact zero-area/repeated triangles. A minimum-height filter
    # would incorrectly remove skinny valid triangles on the connector ramps.
    # No remeshing or smoothing is performed.
    mesh.update_faces(mesh.area_faces > 0.0)
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    removed_triangles = faces_before - len(mesh.faces)
    from .mesh_cleanup import close_micro_triangles
    repair = close_micro_triangles(mesh)
    mesh.export(output / f'{stem}_model.stl')
    printable_mesh = mesh.copy()
    from trimesh.transformations import rotation_matrix
    import numpy as np
    printable_mesh.apply_transform(rotation_matrix(np.pi / 2, [1, 0, 0]))
    printable_mesh.export(output / f'{stem}.stl')
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ValueError('Exported STL is not a closed, consistently oriented positive-volume mesh')
    print('Rendering exported geometry…', flush=True)
    render_review(mesh, output / 'review')
    bbox = module.bounding_box()
    # Adaptive integration also handles the noncircular corner curves.
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    properties = GProp_GProps()
    volume_error = BRepGProp.VolumeProperties_s(module.wrapped, properties, 1e-7, True, False)
    cad_volume = properties.Mass()
    volume_difference = abs(cad_volume - mesh.volume) / max(abs(cad_volume), 1.)
    if cad_volume <= 0 or volume_difference > .001:
        raise ValueError(f'CAD and mesh volume disagree by {volume_difference:.2%}')
    manifest = {
        'module': asdict(spec),
        'name': spec.name,
        'units': 'mm', 'cad_valid': bool(module.is_valid), 'solids': len(module.solids()),
        'boundary_shells': len(module.shells()),
        'cad_volume_mm3': cad_volume,
        'cad_volume_integration_error': volume_error,
        'cad_mesh_volume_relative_difference': volume_difference,
        'model_bounds_mm': [list(bbox.min), list(bbox.max)],
        'stl_watertight': bool(mesh.is_watertight),
        'native_faces': len(module.faces()),
        'stl_triangles': len(mesh.faces),
        'stl_bytes': (output / f'{stem}.stl').stat().st_size,
        'stl_absolute_deflection_mm': .05, 'stl_angular_deflection_radians': .5,
        'stl_control_surface_deflection': True,
        'stl_volume_mm3': float(mesh.volume),
        'removed_degenerate_or_duplicate_triangles': removed_triangles,
        'microscopic_triangle_closure': repair,
        'stl_winding_consistent': bool(mesh.is_winding_consistent),
        'elapsed_seconds': time.monotonic() - started,
        'print_orientation': 'Closed back on Z=0; model rotated +90 degrees about X.',
        'source_files': source_hashes(PROJECT_ROOT),
        'files': {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.glob(f'{stem}*'))
        },
    }
    (output / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def build(output: Path, spec: ModuleSpec = DEFAULT_SPEC):
    from dataclasses import asdict
    configuration = asdict(spec)
    configuration_hash = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    with Build(PROJECT_ROOT, configuration_hash, output=output) as state:
        manifest = _build_into(state.stage, spec)
        if not (manifest.get('cad_valid') is True and manifest.get('solids') == 1
                and manifest.get('stl_watertight') is True
                and manifest.get('stl_winding_consistent') is True
                and manifest.get('stl_volume_mm3', 0) > 0):
            raise ValueError('CAD and mesh validation must pass before publishing')
        write_json(state.stage / 'resolved-parameters.json', configuration)
        destination = state.complete({**manifest, 'passed': True, 'project': 'vault'})
        set_latest(destination, state.output / 'latest' / spec.slug)
    print(f"Built {spec.name}: one valid solid, {manifest['stl_triangles']:,} triangles, "
          f"{manifest['stl_bytes'] / 1000:,.1f} KB STL. Files: {destination}", flush=True)
    return destination


def selected_build(output, spec):
    """Resolve the latest build for this size, retaining legacy output support."""
    pointer = output / 'latest' / spec.slug
    if pointer.exists():
        selected = pointer.resolve()
        verify_files(selected)
        return selected
    if (output / 'manifest.json').is_file():
        verify_files(output)
        return output.resolve()
    legacy = output if spec == DEFAULT_SPEC else output / spec.slug
    if not (legacy / f'{spec.slug}_model.stl').is_file():
        raise RuntimeError('No successful build for this size. Run build first.')
    return legacy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate', 'render'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--family', choices=FAMILIES, default='S')
    parser.add_argument('--depth-units', type=int, default=4)
    parser.add_argument('--height-units', type=int, default=1)
    parser.add_argument('--samples', type=int, default=100_000, help='Area samples and maximum vertex samples per direction')
    parser.add_argument('--tolerance', type=float, default=.25, help='Maximum retained-surface sample deviation in mm, including the simplified outside corners')
    parser.add_argument('--mating-tolerance', type=float, default=.1, help='Stricter maximum deviation in the mechanical interface regions, in mm')
    args = parser.parse_args()
    try:
        spec = ModuleSpec(args.family, args.depth_units, args.height_units)
    except ValueError as error:
        parser.error(str(error))
    if args.output is None:
        args.output = PROJECT_ROOT / 'out'
    if args.samples < 1 or args.tolerance <= 0 or args.mating_tolerance <= 0:
        parser.error('Samples and tolerance must be positive')
    if args.command == 'build':
        build(args.output, spec)
        return
    selected = selected_build(args.output, spec)
    review_root = selected.parent.parent if selected.parent.name == 'builds' else args.output
    review = review_root / 'reviews' / selected.name if (selected / 'manifest.json').is_file() else selected / 'review'
    review.mkdir(parents=True, exist_ok=True)
    if args.command == 'render':
        from .render import render_review
        import trimesh
        render_review(trimesh.load_mesh(selected / f'{spec.slug}_model.stl'), review)
    else:
        if spec != DEFAULT_SPEC:
            parser.error('The full source comparison currently supports S4 1F; other sizes need their own source registration.')
        from .validation import compare
        result = compare(selected / 's4_module_1f_model.stl', review / 'comparison.json',
                         args.samples, args.tolerance, args.mating_tolerance)
        for direction in ['reference_to_model', 'model_to_reference']:
            row = result[direction]
            print(f"{direction}: p95={row['p95_mm']:.4f}, p99={row['p99_mm']:.4f}, max={row['max_mm']:.4f} mm; {row['fraction_within_tolerance']:.2%} within {args.tolerance} mm")
        for name, directions in result['mating_regions'].items():
            maximum = max(row['max_mm'] for row in directions.values())
            print(f"{name}: sampled max={maximum:.4f} mm (limit {args.mating_tolerance:g} mm)")
        if not result['within_sampled_tolerance']:
            raise SystemExit('Surface comparison exceeds the requested tolerance. See comparison.json for locations.')


if __name__ == '__main__':
    main()
