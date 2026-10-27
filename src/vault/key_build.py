"""Build and validate the two-piece key with an immutable export directory.

Run ``python -m vault.key_build --output out --clearance 0.2``.  The two
``stl/key_*.stl`` files are already oriented for printing without supports.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from ._build import run_build, write_json
from .project import PROJECT_ROOT


PRINT_NOTE = (
    "Print flat in the supplied STL orientation, with supports disabled. "
    "Print one gear and one handle; assemble after printing."
)


def _checked_assembly_export(output, stem, parts, *, name):
    """Preserve each named component through a native STEP round trip."""
    from build123d import Compound, export_step, import_step
    from .exports import check_step, precise_volume

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    components, children = [], []
    for part_name, shape in parts.items():
        if not shape.is_valid or len(shape.solids()) != 1 or len(shape.shells()) != 1:
            raise ValueError(f'{part_name}: expected one valid solid with one boundary shell')
        shown = shape.translate((0, 0, 0))
        # A copied assembly child retains its parent.  Detach the copy so
        # STEP exports it as a standalone part instead of an orphan node.
        shown.parent = None
        shown.label = part_name
        path = output / stem / f'{part_name}.step'
        path.parent.mkdir(parents=True, exist_ok=True)
        if not export_step(shown, path):
            raise ValueError(f'{stem}/{part_name}: STEP export failed')
        check_step(shown, path)
        components.append({'name': part_name, 'step': f'{stem}/{part_name}.step', 'kind': 'key'})
        children.append(shown)

    assembly = Compound(label=name, children=children)
    path = output / f'{stem}.step'
    if not export_step(assembly, path):
        raise ValueError(f'{stem}: assembly STEP export failed')
    restored = import_step(path)
    volume = precise_volume(assembly)
    volume_error = abs(precise_volume(restored) - volume) / max(abs(volume), 1.)
    before, after = assembly.bounding_box(), restored.bounding_box()
    bounds_error = max(abs(a - b) for a, b in zip(
        (*before.min, *before.max), (*after.min, *after.max)))
    restored_names = {child.label for child in restored.children}
    report = {
        'passed': bool(restored.is_valid and volume > 0
                       and len(restored.solids()) == len(parts)
                       and len(restored.shells()) == len(parts)
                       and restored_names == set(parts)
                       and volume_error < 1e-5 and bounds_error < 1e-4),
        'solids': len(restored.solids()),
        'boundary_shells': len(restored.shells()),
        'components': sorted(restored_names),
        'volume_relative_error': volume_error,
        'volume_relative_tolerance': 1e-5,
        'bbox_max_error_mm': bounds_error,
    }
    if not report['passed']:
        raise ValueError(f'{stem}: assembly STEP round-trip failed: {report}')
    return restored, report, {'assembly': path.name, 'components': components}


def _assembly_parts(assembly):
    parts = {child.label: child for child in assembly.children}
    if len(assembly.children) != 2 or set(parts) != {'gear', 'handle'}:
        raise ValueError('Key assembly must contain two named children: gear and handle')
    return parts


def _export_key(output, dimensions, spec):
    from .exports import export_part_set, precise_volume
    from .key import build_key_assembly, build_key_parts
    from .render import render_review
    from .tessellation import review_mesh

    parts = build_key_parts(dimensions=dimensions)
    if set(parts) != {'gear', 'handle'}:
        raise ValueError('Key print parts must be exactly gear and handle')
    print_parts = {f'key_{name}': shape for name, shape in parts.items()}
    manifest, print_viewer = export_part_set(
        output, spec, print_parts, kind='key', print_note=PRINT_NOTE)

    assembled_parts = _assembly_parts(build_key_assembly(dimensions=dimensions))
    common = assembled_parts['gear'].intersect(assembled_parts['handle'])
    overlap = sum(abs(precise_volume(piece)) for piece in common) if common else 0.
    if overlap > 1e-6:
        raise ValueError(f'Assembled key parts overlap by {overlap:.9g} mm³')
    assembled, assembly_check, viewer = _checked_assembly_export(
        output, f'{spec.slug}_assembled', assembled_parts, name=spec.name)

    # The gear's print axis is its assembly insertion axis.  Separating it
    # below the handle makes the keyed stem and snap features inspectable.
    gear_bounds = assembled_parts['gear'].bounding_box()
    handle_bounds = assembled_parts['handle'].bounding_box()
    separation = max(12., gear_bounds.max.Z - handle_bounds.min.Z + 5.)
    exploded_parts = {
        'gear': assembled_parts['gear'].translate((0, 0, -separation)),
        'handle': assembled_parts['handle'].translate((0, 0, 0)),
    }
    exploded, exploded_check, exploded_viewer = _checked_assembly_export(
        output, f'{spec.slug}_exploded', exploded_parts, name=f'{spec.name} — exploded')
    render_review(review_mesh(assembled), output / 'review' / 'assembled')
    render_review(review_mesh(exploded), output / 'review' / 'exploded')

    instructions = (
        'SNAP-FIT KEY — PRINT AND ASSEMBLY\n\n'
        'Units: millimetres. Print one of each file:\n'
        '  stl/key_gear.stl\n'
        '  stl/key_handle.stl\n\n'
        'Use the supplied orientations: the original gear bottom and the\n'
        'handle flange underside sit on the build plate.\n'
        'Disable supports. Keep the snap slots and mating socket clear of\n'
        'brim material, stringing, and first-layer elephant foot.\n'
        'Suggested starting point: 0.4 mm nozzle, 0.2 mm layers, and\n'
        '4 perimeters. PETG is preferred for the flexible snap features.\n\n'
        'Align the keyed gear stem with the handle socket. Press the two\n'
        'parts together until the retention features engage and the gear\n'
        'shoulder seats. The keyed joint transmits turning torque.\n'
        'Inspect the assembled and exploded STEP files or review images\n'
        'for the relative orientation before assembly.\n\n'
        f'Designed mating clearance: {dimensions.clearance:g} mm per side.\n'
        'Snap fit has been checked geometrically; printer and material fit\n'
        'still requires a physical test. Adjust --clearance if necessary.\n'
    )
    (output / 'print-assembly.txt').write_text(instructions)
    from zipfile import ZIP_DEFLATED, ZipFile
    with ZipFile(output / 'snap-key-print.zip', 'w', compression=ZIP_DEFLATED) as bundle:
        for name in ('stl/key_gear.stl', 'stl/key_handle.stl', 'print-assembly.txt'):
            bundle.write(output / name, arcname=Path(name).name)
    manifest.update({
        'assembled_step_roundtrip': assembly_check,
        'exploded_step_roundtrip': exploded_check,
        'assembly_overlap_mm3': overlap,
        'key_dimensions': asdict(dimensions),
        'print_instructions': 'print-assembly.txt',
        'print_bundle': 'snap-key-print.zip',
        'review_assemblies': {
            'assembled': viewer['assembly'],
            'exploded': exploded_viewer['assembly'],
            'print_layout': print_viewer['assembly'],
        },
    })
    # Viewer component identities must match the printable manifest parts.
    for description in (viewer, exploded_viewer):
        for component in description['components']:
            component['name'] = f"key_{component['name']}"
    viewer.update({'print_layout': print_viewer, 'exploded': exploded_viewer})
    write_json(output / 'build.json', manifest)
    return manifest, viewer


def build_key(output: Path, dimensions=None):
    """Publish the key only after print and assembly exports pass validation."""
    from .key import KeyDimensions, KeySpec

    dimensions = dimensions or KeyDimensions()
    spec = KeySpec()
    configuration = {
        **asdict(spec), 'part': spec.slug, 'key_dimensions': asdict(dimensions),
    }
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    return run_build(
        PROJECT_ROOT, digest, lambda state: _export_key(state.stage, dimensions, spec),
        parameters=configuration, output=Path(output), aliases=[f'latest/{spec.slug}'])


def main(argv=None):
    from .key import KeyDimensions

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'out',
                        help='immutable build output directory (default: out)')
    parser.add_argument('--clearance', type=float, default=KeyDimensions().clearance,
                        help='mating clearance in millimetres')
    args = parser.parse_args(argv)
    try:
        dimensions = KeyDimensions(clearance=args.clearance)
    except ValueError as error:
        parser.error(str(error))
    build_key(args.output, dimensions)


if __name__ == '__main__':
    main()
