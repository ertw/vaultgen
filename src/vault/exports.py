"""Verify native STEP solids using the cyclone export round-trip checks."""


def precise_volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, properties, 1e-10, True, False)
    return properties.Mass()


def check_step(original, path):
    from build123d import import_step
    restored = import_step(path)
    volume = precise_volume(original)
    restored_volume = precise_volume(restored)
    delta = abs(restored_volume - volume) / max(abs(volume), 1.)
    before, after = original.bounding_box(), restored.bounding_box()
    bounds_delta = max(abs(a - b) for a, b in zip(
        (*before.min, *before.max), (*after.min, *after.max)))
    # Vault's trimmed surfaces shift volume by about 5.4e-6 on STEP import,
    # including with tighter integration and every STEP precision mode.
    # Allow 0.001% while retaining the strict spatial and topology checks.
    passed = (restored.is_valid and len(restored.solids()) == 1
              and len(restored.shells()) == 1 and volume > 0 and restored_volume > 0
              and delta < 1e-5 and bounds_delta < 1e-4)
    report = {'passed': bool(passed), 'volume_relative_error': delta,
              'volume_relative_tolerance': 1e-5, 'bbox_max_error_mm': bounds_delta}
    if not passed:
        raise ValueError(f'STEP round-trip failed for {path.name}: {report}')
    return restored, report


def export_assembly_mesh(output, stem, solid, *, component, print_to_native):
    """Checked finished-part mesh, retaining native coordinates for assembly use."""
    from .tessellation import export_print_mesh
    if not solid.is_valid or len(solid.solids()) != 1 or len(solid.shells()) != 1:
        raise ValueError(f'{stem}: invalid finished assembly solid')
    from build123d import export_step
    relative = f'preview/assembly/{stem}.stl'
    step = f'preview/assembly/{stem}.step'
    (output / step).parent.mkdir(parents=True, exist_ok=True)
    if not export_step(solid, output / step):
        raise ValueError(f'{stem}: finished STEP export failed')
    _, step_check = check_step(solid, output / step)
    mesh = export_print_mesh(solid, output / relative)
    return {'schema': 'vault-assembly-mesh/v1', 'coordinates': 'native',
            'finished': True, 'component': component, 'path': relative,
            'step_path': step, 'step_roundtrip': step_check,
            'print_to_native': list(print_to_native),
            'bounds_mm': mesh.bounds.tolist(), 'cad_valid': True,
            'stl_watertight': bool(mesh.is_watertight)}


def translation_matrix(offset):
    """Column-major homogeneous translation; print origin back to native origin."""
    x, y, z = offset
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]


def export_part_set(output, spec, parts, *, kind, print_note):
    """Export named printable solids with shared per-part and assembly checks."""
    from copy import deepcopy
    from build123d import Compound, export_brep, export_step, import_step
    from .render import render_review
    from .tessellation import export_print_mesh, review_mesh

    from ._build import source_hashes, write_json
    from .project import PROJECT_ROOT
    import time

    if not parts:
        raise ValueError("A part set must contain at least one solid")
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    components, reports, display = [], {}, []
    next_y = 0.
    for stem, solid in parts.items():
        if not solid.is_valid or len(solid.solids()) != 1 or len(solid.shells()) != 1:
            raise ValueError(f'{stem}: expected one valid solid with one boundary shell')
        bounds = solid.bounding_box()
        printable = solid.translate((-bounds.min.X, -bounds.min.Y, -bounds.min.Z))
        # Identical left/right parts may share an OpenCascade shape. Give each
        # assembly item its own shape so STEP retains both component names.
        shown = deepcopy(printable).translate((0, next_y, 0))
        shown.label = stem
        next_y = shown.bounding_box().max.Y + 5.
        print(f'Exporting {stem} STEP and print STL…', flush=True)
        for shape, suffix in ((shown, ''), (printable, '_print')):
            path = output / f'{stem}{suffix}.step'
            if not export_step(shape, path):
                raise ValueError(f'{stem}{suffix}: STEP export failed')
            _, report = check_step(shape, path)
            if suffix:
                print_check = report
            else:
                step_check = report
        if not export_brep(shown, output / f'{stem}.brep'):
            raise ValueError(f'{stem}: BREP export failed')
        mesh = export_print_mesh(printable, output / 'stl' / f'{stem}.stl')
        reports[stem] = {
            'assembly_mesh': export_assembly_mesh(output, stem, solid,
                component=stem.rsplit('_', 1)[-1], print_to_native=translation_matrix(bounds.min)),
            'kind': kind, 'cad_valid': True, 'solids': 1, 'boundary_shells': 1,
            'cad_volume_mm3': precise_volume(solid),
            'step_roundtrip': step_check, 'print_step_roundtrip': print_check,
            'print_bbox_mm': list(printable.bounding_box().size),
            'print_note': print_note,
            'stl_watertight': bool(mesh.is_watertight),
            'stl_winding_consistent': bool(mesh.is_winding_consistent),
        }
        components.append({'name': stem, 'step': f'{stem}.step', 'kind': kind})
        display.append(shown)

    assembly = Compound(label=spec.name, children=display)
    path = output / f'{spec.slug}.step'
    if not export_step(assembly, path):
        raise ValueError('Part assembly STEP export failed')
    restored = import_step(path)
    volume = precise_volume(assembly)
    volume_delta = abs(precise_volume(restored) - volume) / max(volume, 1.)
    before, after = assembly.bounding_box(), restored.bounding_box()
    bounds_delta = max(abs(a - b) for a, b in zip(
        (*before.min, *before.max), (*after.min, *after.max)))
    component_names = {child.label for child in restored.children}
    expected_names = {item['name'] for item in components}
    assembly_check = {
        'passed': bool(restored.is_valid and len(restored.solids()) == len(parts)
                       and len(restored.shells()) == len(parts) and volume > 0
                       and component_names == expected_names
                       and volume_delta < 1e-5 and bounds_delta < 1e-4),
        'solids': len(restored.solids()), 'boundary_shells': len(restored.shells()),
        'components': sorted(component_names),
        'volume_relative_error': volume_delta, 'volume_relative_tolerance': 1e-5,
        'bbox_max_error_mm': bounds_delta,
    }
    if not assembly_check['passed']:
        raise ValueError(f'Part assembly STEP round-trip failed: {assembly_check}')
    render_review(review_mesh(restored), output / 'review')
    manifest = {
        'passed': True, 'project': 'vault', 'name': spec.name, 'units': 'mm',
        'status': 'Completed CAD build', 'cad_valid': True, 'solids': len(parts),
        'boundary_shells': len(parts), 'cad_volume_mm3': volume,
        'model_bounds_mm': [list(before.min), list(before.max)],
        'step_roundtrip': assembly_check, 'parts': reports,
        'elapsed_seconds': time.monotonic() - started,
        'source_files': source_hashes(PROJECT_ROOT),
    }
    write_json(output / 'build.json', manifest)
    return manifest, {'assembly': path.name, 'components': components}
