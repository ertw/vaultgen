"""Audit integrated Gridfinity sockets, nominal bins, and unchanged interfaces.

Examples after sourcing .local-env:
    python tools/check_gridfinity.py --case S4:1
    python tools/check_gridfinity.py --case L7:2:3
    python tools/check_gridfinity.py --case S3:1:0  # floorless Gridfinity

This checks CAD geometry, including rounded bin corners and multi-cell bridges;
it does not establish printed fit, bin height clearance, or loaded stiffness.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

from build123d import Compound, Plane, Shape, Solid, import_step
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut

from vault.box import BoxSpec, build_box
from vault.gridfinity import GridfinityLayout
from vault.shell import _rounded_rect


TOLERANCE_MM3 = 1e-5


def volume(shape):
    return sum(abs(solid.volume) for solid in shape.solids())


def boolean(left, right, operation):
    result = operation(left.wrapped, right.wrapped)
    if not result.IsDone():
        raise RuntimeError('Gridfinity audit Boolean failed')
    return Shape.cast(result.Shape())


def intersection_volume(left, right):
    return volume(boolean(left, right, BRepAlgoAPI_Common))


def nominal_bin_base(columns=1, rows=1):
    """Independent bin witness from the primary standard.scad dimensions.

    Includes every foot and a continuous 2.25 mm bridge under the bin body.
    These deliberately do not reuse the constructor's socket dimensions.
    """
    sections = []
    for z, size, radius in ((0, 35.6, .8), (.8, 37.2, 1.6),
                            (2.6, 37.2, 1.6), (4.75, 41.5, 3.75)):
        sections.append(_rounded_rect(-size/2, -size/2, size/2, size/2,
                                      radius, lambda x, y: (x, y, z)).outer_wire())
    foot = Solid.make_loft(sections, ruled=True)
    feet = [foot.translate(((column-(columns-1)/2)*42, (row-(rows-1)/2)*42, 0))
            for row in range(rows) for column in range(columns)]
    x, y = (columns*42-.5)/2, (rows*42-.5)/2
    bridge = Solid.extrude(_rounded_rect(-x, -y, x, y, 3.75,
                                         lambda x, y: (x, y, 4.75)), (0, 0, 2.25))
    return Compound(children=[*feet, bridge])


def audit_gridfinity(plain, grid, spec):
    layout = GridfinityLayout(spec)
    floorless = spec.box_floor == 0
    added = boolean(grid, plain, BRepAlgoAPI_Cut)
    removed = boolean(plain, grid, BRepAlgoAPI_Cut)
    removed_volume = volume(removed)
    allowed = Solid.make_box(layout.x_max-layout.x_min,
                             layout.y_max-layout.y_min, 5.0,
                             Plane(origin=(layout.x_min, layout.y_min, layout.floor_z)))
    outside_volume = volume(boolean(added, allowed, BRepAlgoAPI_Cut))
    a, b = plain.bounding_box(), grid.bounding_box()
    bounds_error = max(abs(x-y) for first, second in ((a.min, b.min), (a.max, b.max))
                       for x, y in zip(first, second))
    removal_outside_openings = 0.0
    material_in_openings = 0.0
    if floorless:
        # Independently specify the complete lower opening. Checking the
        # removed solid, not just center probes, protects the web foundations
        # and also catches a residual floor or the base's union skin.
        openings = Compound(children=[Solid.extrude(_rounded_rect(
            x-18.15, y-18.15, x+18.15, y+18.15, 1.15,
            lambda x, y: (x, y, 5.0)), (0, 0, .81))
            for x, y in layout.centers])
        removal_outside_openings = volume(boolean(removed, openings, BRepAlgoAPI_Cut))
        material_in_openings = intersection_volume(grid, openings)
        floor_checks = [not grid.is_inside((x+dx, y+dy, z))
                        for x, y in layout.centers
                        for dx, dy in ((0, 0), (17.5, 0), (17.5, 17.5))
                        for z in (5.01, 5.79, 5.81)]
        removal_ok = (removed_volume > 1 and removal_outside_openings < TOLERANCE_MM3
                      and material_in_openings < TOLERANCE_MM3)
    else:
        floor_checks = [grid.is_inside((x, y, 5.01))
                        and grid.is_inside((x, y, layout.floor_z-.01))
                        and not grid.is_inside((x, y, layout.floor_z+.01))
                        for x, y in layout.centers]
        removal_ok = removed_volume < TOLERANCE_MM3
    # Single-cell bins seat on the matching lower chamfer even when the floor
    # is open; closed-floor variants also retain material under the foot. The
    # continuous bridge of a multi-cell bin rests on the 5 mm webs, so its
    # 4.75 mm feet start 0.25 mm above that floor.
    single = nominal_bin_base()
    corners = (layout.centers[0], layout.centers[layout.columns-1],
               layout.centers[-layout.columns], layout.centers[-1])
    single_collisions = [intersection_volume(grid, single.translate((x, y, layout.floor_z)))
                         for x, y in corners]
    multiple = nominal_bin_base(layout.columns, layout.rows).translate(
        (0, (layout.y_min+layout.y_max)/2, layout.floor_z+.25))
    multi_collision = intersection_volume(grid, multiple)
    # A lateral error must hit a socket wall: a missing web cannot pass by
    # merely having a large enough cavity around all the positive witnesses.
    x, y = corners[0]
    displaced_collision = intersection_volume(grid, single.translate((x+1, y, layout.floor_z)))
    lowered_single_collision = intersection_volume(
        grid, single.translate((x, y, layout.floor_z-.1)))
    lowered_multi_collision = intersection_volume(grid, multiple.translate((0, 0, -.1)))
    valid = bool(grid.is_valid and len(grid.solids()) == 1 and len(grid.shells()) == 1)
    passed = (valid and removal_ok
              and outside_volume < TOLERANCE_MM3 and bounds_error < 1e-5
              and all(floor_checks) and max(single_collisions) < TOLERANCE_MM3
              and multi_collision < TOLERANCE_MM3 and displaced_collision > .1
              and lowered_single_collision > .1 and lowered_multi_collision > .1)
    return {
        'passed': passed, 'spec': asdict(spec), 'layout': layout.notes(),
        'valid_single_solid_and_shell': valid,
        'removed_volume_mm3': removed_volume,
        'added_volume_mm3': volume(added),
        'addition_outside_grid_mm3': outside_volume,
        'maximum_bounds_error_mm': bounds_error,
        'closed_floor_checks': all(floor_checks) if not floorless else None,
        'open_cell_floor_checks': all(floor_checks) if floorless else None,
        'removal_outside_cell_openings_mm3': removal_outside_openings,
        'material_remaining_in_cell_openings_mm3': material_in_openings,
        'single_bin_corner_collisions_mm3': single_collisions,
        'full_grid_bin_collision_mm3': multi_collision,
        'misaligned_bin_collision_mm3': displaced_collision,
        'lowered_single_bin_collision_mm3': lowered_single_collision,
        'lowered_full_grid_bin_collision_mm3': lowered_multi_collision,
    }


def parse_case(value):
    try:
        size, height, *floor = value.split(':')
        return BoxSpec(size[0].upper(), int(size[1:]), int(height),
                       float(floor[0]) if floor else .8, 'gridfinity')
    except (ValueError, IndexError) as error:
        raise argparse.ArgumentTypeError('Use S4:1 or L7:2:3 (size:height[:floor])') from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', type=parse_case)
    parser.add_argument('--box-rear-pattern', choices=('plain', 'waffle', 'miura'), default='plain')
    parser.add_argument('--plain-step', type=Path)
    parser.add_argument('--gridfinity-step', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    cases = [replace(spec, box_rear_pattern=args.box_rear_pattern)
             for spec in (args.case or [BoxSpec(box_variant='gridfinity')])]
    if bool(args.plain_step) != bool(args.gridfinity_step) or (args.plain_step and len(cases) != 1):
        parser.error('STEP comparison requires both paths and one case')
    reports = []
    for spec in cases:
        plain = import_step(args.plain_step) if args.plain_step else build_box(
            spec=replace(spec, box_variant='plain', box_floor=max(.8, spec.box_floor)))
        grid = import_step(args.gridfinity_step) if args.gridfinity_step else build_box(spec=spec)
        reports.append(audit_gridfinity(plain, grid, spec))
    report = {
        'schema': 'vault-gridfinity-fit/v1', 'passed': all(item['passed'] for item in reports),
        'cases': reports,
        'sources': [
            'https://github.com/kennetek/gridfinity-rebuilt-openscad/blob/main/src/core/standard.scad',
            'https://github.com/kennetek/gridfinity-rebuilt-openscad/blob/main/src/core/gridfinity-baseplate.scad',
        ],
        'limitations': 'Nominal CAD fit only; not printed fit, bin height clearance, or loaded stiffness.',
    }
    if args.plain_step:
        report['step_inputs'] = {kind: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                                 for kind, path in (('plain', args.plain_step), ('gridfinity', args.gridfinity_step))}
    output = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output, end='')
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
