"""Registered facade color exports alongside the ordinary single-solid build."""
from build123d import export_step

from .build import print_orientation
from .exports import check_step, precise_volume, export_assembly_mesh
from .facade_markings import build_facade_materials
from .label_build import _write_3mf
from .tessellation import export_print_mesh


PRINT_NOTE = (
    'For lock/unlock markings, open the 3MF as one multipart object. '
    'Assign the body to primary filament and both icons to secondary filament. '
    'The flush inlays are 0.6 mm deep. Keep the supplied orientation and shared '
    'coordinates; do not arrange the color parts separately. '
    'The ordinary STL is a single-color alternative. '
)


def export_facade_materials(output, spec, facade, print_to_native):
    materials = build_facade_materials(facade)
    reports, meshes = {}, {}
    for name, part in materials.items():
        shape = part['shape']
        printable = print_orientation(shape, spec)
        stem = f'{spec.slug}_{name}'
        checks = {}
        for solid, suffix in ((shape, ''), (printable, '_print')):
            relative = f'multicolor/{stem}{suffix}.step'
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not export_step(solid, path):
                raise ValueError(f'{stem}: color STEP export failed')
            _, checks[suffix or 'native'] = check_step(solid, path)
        assembly = export_assembly_mesh(output, stem, shape, component=name,
                                        print_to_native=print_to_native)
        print_path = f'preview/materials/{stem}.stl'
        meshes[stem] = export_print_mesh(printable, output / print_path)
        reports[name] = {'role': part['role'], 'color': part['color'],
                         'assembly_mesh': assembly, 'print_path': print_path,
                         'step_roundtrip': checks['native'],
                         'print_step_roundtrip': checks['_print'],
                         'cad_volume_mm3': precise_volume(shape),
                         'stl_watertight': bool(meshes[stem].is_watertight)}
    original_volume = precise_volume(facade)
    material_volume = sum(part['cad_volume_mm3'] for part in reports.values())
    if abs(original_volume - material_volume) / original_volume > 1e-6:
        raise ValueError('Facade color parts do not conserve the original volume')
    three_mf = f'{spec.slug}.3mf'
    check = _write_3mf(output / three_mf, meshes,
                       {f'{spec.slug}_{name}': part['color'] for name, part in materials.items()},
                       name=spec.name, application='Vaultgen native facade',
                       material_roles={f'{spec.slug}_{name}': part['role'] for name, part in materials.items()})
    return {'materials': reports, 'multicolor_3mf': three_mf,
            'multicolor_roundtrip': check}
