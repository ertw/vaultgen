"""Select native parts and publish checked builds for CLI and worker callers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

from .project import PROJECT_ROOT
from .spec import DEFAULT_SPEC, ModuleSpec
from ._build import run_build, source_hashes, verify_files


def _build_into(output: Path, spec: ModuleSpec = DEFAULT_SPEC):
    from .model import build_module

    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    print('Building native shell and mechanical connectors…', flush=True)
    if part_kind(spec) == 'facade':
        from .facade import build_facade
        module = build_facade(spec=spec)
        finished = module
    elif part_kind(spec) == 'box':
        from .box import build_box
        module = build_box(spec=spec)
        finished = build_box(spec=spec, include_supports=False)
    else:
        module = build_module(spec=spec, progress=lambda message: print(message, flush=True))
        finished = build_module(spec=spec, include_supports=False)
    return _export_into(module, output, started, spec, finished=finished)


def _export_into(module, output: Path, started: float, spec: ModuleSpec = DEFAULT_SPEC, *, finished=None):
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
    assembly_mesh = None
    if finished is not None:
        print('Exporting finished assembly preview…', flush=True)
        from .exports import export_assembly_mesh, translation_matrix
        # Shelled facades put their front on the bed; other facade/module
        # exports put the back on the bed. Record each exact inverse placement.
        print_to_native = (translation_matrix((0, 0, module.bounding_box().min.Z))
                           if part_kind(spec) == 'box' else
                           [1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 10, 0, 1]
                           if part_kind(spec) == 'facade' and spec.facade_floor == 0.8 else
                           [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1])
        assembly_mesh = export_assembly_mesh(output, stem, finished, component='single',
                                             print_to_native=print_to_native)
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
        'assembly_mesh': assembly_mesh,
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
        'print_orientation': (('Gridfinity frame on Z=0; sockets remain open underneath. '
                               if getattr(spec, 'box_floor', .8) == 0 else 'Closed bottom on Z=0. ')
                              + 'Remove the breakaway runner sheets before assembly.' if part_kind(spec) == 'box' else
                              'Closed back on Z=0; model rotated +90 degrees about X. '
                              'Remove the breakaway webs under the runner-mouth lips in every bay and tier before assembly.'
                              if part_kind(spec) == 'module' else
                              'Front face on Z=0; rear cavities open upward. Model rotated -90 degrees about X. '
                              'The label recess and lock lips may need local support; inspect them in the slicer.'
                              if getattr(spec, 'facade_floor', 'default') == 0.8 else
                              'Rear face on Z=0; model rotated +90 degrees about X. Use supports beneath recessed faces.'),
        'source_files': source_hashes(PROJECT_ROOT),
        'files': {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.glob(f'{stem}*'))
        },
    }
    if isinstance(spec, ModuleSpec) and spec.wall_pattern != 'plain':
        manifest['print_orientation'] += (
            f' Corrugated patterned facets target {2 * spec.pattern_line_width:g} mm normal thickness '
            f'for two {spec.pattern_line_width:g} mm extrusion lines with a 0.6 mm nozzle; '
            'folds, transitions and structural lands remain thicker. Verify the perimeter paths in your slicer.'
            if spec.pattern_construction == 'corrugated' else
            f' Pattern valleys retain at least {2 * spec.pattern_line_width:g} mm for two '
            f'{spec.pattern_line_width:g} mm extrusion lines with a 0.6 mm nozzle; crests and '
            'structural lands remain thicker. Verify the perimeter paths in your slicer.')
    if part_kind(spec) == 'box' and getattr(spec, 'box_variant', 'plain') == 'gridfinity':
        from .gridfinity import GridfinityLayout
        manifest['gridfinity'] = GridfinityLayout(spec).notes()
        manifest['print_orientation'] += (
            ' Integral Gridfinity pockets use a 42 mm grid inside the drawer. '
            + ('The 5 mm grid has no closed floor. ' if spec.box_floor == 0 else
               'The grid rises 5 mm above the selected floor. ')
            + 'Check bin height and printed fit before filling the drawer.')
    if part_kind(spec) == 'box' and getattr(spec, 'box_rear_pattern', 'plain') != 'plain':
        manifest['print_orientation'] += (
            ' The corrugated rear wall uses a 14 mm pattern pitch and targets 1.3 mm '
            'normal facet thickness for two 0.65 mm extrusion lines with a 0.6 mm nozzle. '
            'Folds and structural borders remain thicker. Verify perimeter paths in your slicer.')
    (output / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def part_kind(spec):
    if hasattr(spec, 'accessory'):
        return spec.accessory
    for kind in ('runner_guides', 'runner_slides'):
        if spec.slug.endswith('_' + kind):
            return kind
    if spec.slug.endswith('_facade') or '_facade_floor_' in spec.slug:
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
    if part_kind(spec) == 'facade' and spec.facade_floor == 0.8:
        from build123d import Axis
        # The facade front datum is Y=10; opening its rear pockets upward
        # avoids bridging the broad 0.8 mm floor over an unsupported cavity.
        return module.rotate(Axis.X, -90).translate((0, 0, 10))
    from .model import print_orientation as orient_module
    return orient_module(module)


def build(output: Path, spec: ModuleSpec = DEFAULT_SPEC):
    if hasattr(spec, 'accessory'):
        from .accessories import build_accessory
        return build_accessory(output, spec)
    if part_kind(spec) in {'runner_guides', 'runner_slides'}:
        return build_runners(output, spec)
    if part_kind(spec) == 'rail':
        return build_rails(output, spec)
    from dataclasses import asdict, replace
    if isinstance(spec, ModuleSpec):
        spec = replace(spec, drawer_rows=1)
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
            'assembly_mesh': manifest.get('assembly_mesh'),
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


def select_spec(part, family='S', depth_units=4, height_units=1, *, box_floor=0.8, module_rear=0.9,
                drawer_columns=1, drawer_rows=1, wall_pattern='plain', pattern_pitch=14.0,
                pattern_depth=1.7, pattern_line_width=0.65, pattern_faces='all', pattern_construction='recessed',
                box_variant='plain', box_rear_pattern='plain', facade_floor='default'):
    """Resolve the same native constructors for the CLI and web generator."""
    from .generator import ACCESSORY_PARTS
    if part in ACCESSORY_PARTS:
        from .accessories import AccessorySpec
        return AccessorySpec(part)
    module_spec = ModuleSpec(family, depth_units, height_units, module_rear, drawer_columns, drawer_rows,
                             wall_pattern, pattern_pitch, pattern_depth, pattern_line_width, pattern_faces,
                             pattern_construction)
    if part == 'module':
        from dataclasses import replace
        return replace(module_spec, drawer_rows=1)
    family = module_spec.drawer_family
    height_units = module_spec.drawer_height_units
    if part == 'box':
        from .box import BoxSpec
        return BoxSpec(family, depth_units, height_units, box_floor, box_variant, box_rear_pattern)
    if part == 'facade':
        from .facade import FacadeSpec
        return FacadeSpec(family, height_units, facade_floor=facade_floor)
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
