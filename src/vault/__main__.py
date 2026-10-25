"""Build, export, render, and measure the reconstruction."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from .reference import PROJECT_ROOT
from .spec import DEFAULT_SPEC, FAMILIES, ModuleSpec
from ._build import run_build, source_hashes, verify_files


def _build_into(output: Path, spec: ModuleSpec = DEFAULT_SPEC):
    from .model import build_module

    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    print('Building native shell and mechanical connectors…', flush=True)
    if part_kind(spec) == 'facade':
        from .facade import build_facade
        module = build_facade(spec=spec)
    elif part_kind(spec) == 'box':
        from .box import build_box
        module = build_box(spec=spec)
    else:
        module = build_module(spec=spec, progress=lambda message: print(message, flush=True))
    return _export_into(module, output, started, spec)


def _export_into(module, output: Path, started: float, spec: ModuleSpec = DEFAULT_SPEC):
    """Export and check an already constructed native model."""
    from build123d import export_brep, export_step
    from .render import render_review
    from dataclasses import asdict

    output.mkdir(parents=True, exist_ok=True)
    stem = spec.slug
    print('Exporting STEP solids and BREP…', flush=True)
    if not module.is_valid or len(module.solids()) != 1 or len(module.shells()) != 1:
        raise ValueError('Expected one valid solid with one boundary shell')
    from .exports import check_step
    if not export_step(module, output / f'{stem}.step'):
        raise ValueError('STEP export failed')
    restored, step_check = check_step(module, output / f'{stem}.step')
    printable = print_orientation(module, spec)
    if not export_step(printable, output / f'{stem}_print.step'):
        raise ValueError('Print STEP export failed')
    _, print_step_check = check_step(printable, output / f'{stem}_print.step')
    if not export_brep(module, output / f'{stem}.brep'):
        raise ValueError('BREP export failed')
    from .tessellation import review_mesh
    mesh = review_mesh(restored)
    print('Exporting print-oriented STL…', flush=True)
    from .tessellation import export_print_mesh
    print_stl = output / 'stl' / f'{stem}.stl'
    export_print_mesh(printable, print_stl)
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
        'cad_review_mesh_volume_relative_difference': volume_difference,
        'model_bounds_mm': [list(bbox.min), list(bbox.max)],
        'native_faces': len(module.faces()),
        'step_roundtrip': step_check,
        'print_step_roundtrip': print_step_check,
        'step_bytes': (output / f'{stem}.step').stat().st_size,
        'elapsed_seconds': time.monotonic() - started,
        'print_bbox_mm': list(printable.bounding_box().size),
        'print_orientation': ('Closed bottom on Z=0. Remove the breakaway runner sheets before assembly.' if part_kind(spec) == 'box' else
                              'Closed back on Z=0; model rotated +90 degrees about X. '
                              'Remove the breakaway webs under both runner-mouth lips before assembly.'
                              if part_kind(spec) == 'module' else
                              'Rear face on Z=0; model rotated +90 degrees about X. Use supports beneath recessed faces.'),
        'source_files': source_hashes(PROJECT_ROOT),
        'files': {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.glob(f'{stem}*'))
        },
    }
    (output / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def part_kind(spec):
    for kind in ('runner_guides', 'runner_slides'):
        if spec.slug.endswith('_' + kind):
            return kind
    if spec.slug.endswith('_facade'):
        return 'facade'
    if '_box_' in spec.slug:
        return 'box'
    if spec.slug.endswith('_geared_rails'):
        return 'rail'
    return 'module'


def print_orientation(module, spec):
    """Place each part's intended print face on the build plate."""
    if part_kind(spec) == 'box':
        from .box import print_orientation as orient_box
        return orient_box(module)
    from .model import print_orientation as orient_module
    return orient_module(module)


def build(output: Path, spec: ModuleSpec = DEFAULT_SPEC):
    if part_kind(spec) in {'runner_guides', 'runner_slides'}:
        return build_runners(output, spec)
    if part_kind(spec) == 'rail':
        return build_rails(output, spec)
    from dataclasses import asdict
    configuration = {**asdict(spec), 'part': spec.slug}
    if part_kind(spec) in {'facade', 'module'}:
        from .shadow_gap import DEFAULT_GAP
        configuration['shadow_gap'] = asdict(DEFAULT_GAP)
    configuration_hash = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    def generate(state):
        manifest = _build_into(state.stage, spec)
        if not (manifest.get('cad_valid') is True and manifest.get('solids') == 1
                and manifest.get('boundary_shells') == 1
                and manifest.get('step_roundtrip', {}).get('passed') is True
                and manifest.get('print_step_roundtrip', {}).get('passed') is True):
            raise ValueError('CAD and STEP validation must pass before publishing')
        viewer = {
            'build_id': state.id, 'assembly': f'{spec.slug}.step',
            'components': [{'name': spec.slug, 'step': f'{spec.slug}.step', 'kind': part_kind(spec)}],
        }
        manifest.update(viewer='viewer.json', status='Completed CAD build', parts={spec.slug: {
            'kind': part_kind(spec), 'print_note': manifest.get('print_orientation', ''),
            'print_bbox_mm': manifest.get('print_bbox_mm', []),
        }})
        return {**manifest, 'passed': True, 'project': 'vault'}, viewer
    return run_build(PROJECT_ROOT, configuration_hash, generate, parameters=configuration,
                     output=output, aliases=[f'latest/{spec.slug}'])


def _export_rails(output: Path, spec=None):
    """Export both rail variants through the shared multipart checks."""
    from .exports import export_part_set
    from .geared_rails import SPEC, build_gear_rail
    spec = spec or SPEC
    parts = {f'{spec.family.lower()}_geared_rail_{variant}':
             (build_gear_rail(retained=retained) if spec == SPEC else
              build_gear_rail(retained=retained, spec=spec))
             for variant, retained in (('plain', False), ('retained', True))}
    return export_part_set(output, spec, parts, kind='rail',
                           print_note='Flat broad face on Z=0; teeth lie in the build plate plane.')


def _export_runners(output: Path, spec):
    from .exports import export_part_set
    kind = part_kind(spec)
    if kind == 'runner_guides':
        from .runner_guides import build_runner_guides
        parts = build_runner_guides(spec=spec)
    else:
        from .runner_slides import build_runner_slides
        parts = build_runner_slides(spec=spec)
    parts = {f'{spec.slug}_{name}': solid for name, solid in parts.items()}
    return export_part_set(output, spec, parts, kind=kind,
                           print_note='Print flat in the supplied orientation. One left/right pair per populated '
                           'runner tier; repeat the pair for additional tiers. Match the guide and slide depths.')


def build_runners(output: Path, spec):
    from dataclasses import asdict
    configuration = {**asdict(spec), 'part': spec.slug}
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    return run_build(PROJECT_ROOT, digest, lambda state: _export_runners(state.stage, spec),
                     parameters=configuration, output=output,
                     aliases=[f'latest/{spec.slug}'])


def build_rails(output: Path, spec=None):
    """Publish a two-part rail set only after each export has passed validation."""
    from dataclasses import asdict
    from .geared_rails import SPEC, rail_dimensions
    spec = spec or SPEC
    configuration = {**asdict(spec), 'part': spec.slug,
                     'geared_rails': asdict(rail_dimensions(spec.family))}
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    return run_build(PROJECT_ROOT, digest, lambda state: _export_rails(state.stage, spec),
                     parameters=configuration, output=output,
                     aliases=[f'latest/{spec.slug}'])


def build_preview(configuration):
    if configuration in ('x4_runner_guides', 'x4_runner_slides'):
        return build(PROJECT_ROOT / 'out', select_spec(configuration[3:]))
    if configuration == 's_geared_rails':
        from .geared_rails import SPEC
        return build(PROJECT_ROOT / 'out', SPEC)
    if configuration == 's4_box_1f':
        from .box import SPEC
        return build(PROJECT_ROOT / 'out', SPEC)
    if configuration == 's1f_facade':
        from .facade import SPEC
        return build(PROJECT_ROOT / 'out', SPEC)
    family, depth, height = configuration.split('-')
    return build(PROJECT_ROOT / 'out', ModuleSpec(family, int(depth), int(height)))


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
    if not any((legacy / name).is_file() for name in (f'{spec.slug}.step', f'{spec.slug}_model.stl')):
        raise RuntimeError('No successful build for this size. Run build first.')
    return legacy


def select_spec(part, family='S', depth_units=4, height_units=1, *, box_floor=0.8, module_rear=0.9):
    """Resolve the same native constructors for the CLI and web generator."""
    if part == 'module':
        return ModuleSpec(family, depth_units, height_units, module_rear)
    if part == 'box':
        from .box import BoxSpec
        return BoxSpec(family, depth_units, height_units, box_floor)
    if part == 'facade':
        from .facade import FacadeSpec
        return FacadeSpec(family, height_units)
    if part == 'rails':
        from .geared_rails import GearRailSpec
        return GearRailSpec(family)
    if part in ('runner_guides', 'runner_slides'):
        if family not in ('S', 'M', 'L') or type(height_units) is not int or height_units not in (1, 2):
            raise ValueError('Runner pairs support S/M/L drawers in 1F or 2F')
        if part == 'runner_guides':
            from .runner_guides import RunnerGuideSpec
            return RunnerGuideSpec(depth_units)
        from .runner_slides import RunnerSlideSpec
        return RunnerSlideSpec(depth_units)
    raise ValueError('Unknown part')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate', 'render'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--part', choices=['module', 'facade', 'box', 'rails', 'runner_guides', 'runner_slides'], default='module')
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
    try:
        spec = select_spec(args.part, args.family, args.depth_units, args.height_units)
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
    model_path = selected / f'{spec.slug}.step'
    if not model_path.is_file():
        model_path = selected / f'{spec.slug}_model.stl'
    if args.command == 'render':
        from .render import render_review
        from .tessellation import load_model
        render_review(load_model(model_path), review)
    else:
        if spec != DEFAULT_SPEC:
            parser.error('The full source comparison currently supports S4 1F; other sizes need their own source registration.')
        from .validation import compare
        result = compare(model_path, review / 'comparison.json',
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
