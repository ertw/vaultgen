"""Audit a patterned box rear against its plain native mechanical interfaces.

Checks exact containment of material changes and samples thickness along native
face normals. Optional STEP inputs audit immutable exported solids and record
their hashes. This does not certify slicer paths, strength or physical fit.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

from build123d import Axis, import_step
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin

from vault.box import BoxSpec, build_box
from vault.box_wall_patterns import apply_box_rear_pattern
from vault.drawer import DrawerLayout
from vault.spec import wall_target_thickness
if __package__:
    from .check_wall_patterns import box_between, intersection_volume, volume
else:
    from check_wall_patterns import box_between, intersection_volume, volume


def allowed_rear_volume(spec):
    """Independent removal bounds leaving corners, floor fillet and rim intact."""
    layout = DrawerLayout(spec)
    # Inner cavity is 63.6+dx wide with R3.5 corners. Keep another 3 mm land.
    backing = wall_target_thickness(spec) if spec.wall_perimeters in (1, 2) else 1.3
    half = 64.9 - backing + layout.width_delta - 3.5 - 3.0
    return box_between((-half, 2.3, 5 + max(.8, spec.box_floor) + 1 + 3),
                       (half, 5.3, 42.5 + layout.height_delta - 3))


def allowed_side_volumes(spec):
    """Only the interior cavity may move to change runner backing thickness.

    The channel surfaces start at |X|=64.9+width_delta and stay fixed. These
    bounds include the inside cavity's rear/front corner radii and floor fillet,
    but exclude all exterior runner surfaces, supports and front hardware.
    """
    if spec.wall_perimeters not in (1, 2):
        return []
    layout = DrawerLayout(spec)
    inner = min(63.6, 64.9-wall_target_thickness(spec)) - 3.5 - 1.0 + layout.width_delta
    return [box_between((lo, 5.3, 5+max(.8, spec.box_floor)),
                         (hi, 181.5+layout.depth_delta, 42.5+layout.height_delta))
            for lo, hi in ((inner, 64.9+layout.width_delta),
                           (-64.9-layout.width_delta, -inner))]


def rear_normal_web_samples(patterned, spec, limit=12):
    """Sample native exterior flats and slopes toward their inner surfaces."""
    bounds = allowed_rear_volume(spec).bounding_box()
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(patterned.wrapped, 1e-6)
    samples, seen = [], set()
    for face in sorted(patterned.faces(), key=lambda item: item.area, reverse=True):
        if len(samples) >= limit:
            break
        point = face.position_at(.5, .5)
        if not all(a-1e-6 <= p <= b+1e-6
                   for a, p, b in zip(bounds.min, point, bounds.max)):
            continue
        if face.distance_to(point) > 1e-6:
            continue
        normal = face.normal_at(point)
        if normal.Y >= -.1:
            continue
        key = tuple(round(component, 2) for component in normal)
        if key in seen:
            continue
        start = point + normal * .01
        intersector.Perform(gp_Lin(Axis(start, -normal).wrapped), 0., 9.)
        if not intersector.IsDone():
            continue
        hits = sorted(intersector.WParameter(i) for i in range(1, intersector.NbPnt()+1))
        distinct = []
        for hit in hits:
            if not distinct or hit-distinct[-1] > 1e-5:
                distinct.append(hit)
        if len(distinct) < 2 or abs(distinct[0]-.01) > 1e-4:
            continue
        thickness = distinct[1] - distinct[0]
        seen.add(key)
        samples.append({'point_mm': tuple(point), 'normal': tuple(normal),
                        'thickness_mm': thickness,
                        'minimum_passed': thickness >= wall_target_thickness(spec)-.01,
                        'at_nominal_two_lines': abs(thickness-wall_target_thickness(spec)) <= .02})
    return samples


def audit_box_rear_pattern(plain, patterned, spec):
    """Check complete box geometry, including supports and optional base."""
    permitted = allowed_rear_volume(spec)
    removed = plain.cut(patterned)
    added = patterned.cut(plain)
    added_volume = volume(added)
    sides = allowed_side_volumes(spec)
    outside_volume = volume(removed.cut(permitted, *sides))
    added_outside = 0.0
    if added_volume > 1e-8:
        added_outside = volume(added.cut(*sides) if sides else added)
        outside_volume += added_outside
    bounds_error = max(abs(a-b) for end in ('min', 'max') for a, b in zip(
        getattr(plain.bounding_box(), end), getattr(patterned.bounding_box(), end)))
    samples = rear_normal_web_samples(patterned, spec)
    layout = DrawerLayout(spec)
    protected = [
        ('floor_and_fillet', box_between((-200, 2, 4), (200, 400, 6+max(.8, spec.box_floor)))),
        ('front_interfaces', box_between((-200, 170+layout.depth_delta, 4),
                                         (200, 190+layout.depth_delta, 92))),
        ('runners_and_supports', box_between((-200, 25, 15),
                                             (200, 170+layout.depth_delta, 85))),
    ]
    if sides:
        # A thicker backing adds material inside the cavity, and a thinner one
        # removes it there. The floor plane, runner profile and front mechanisms
        # remain independently protected outside those explicit cavity bands.
        protected = [(name, envelope.cut(*sides)) for name, envelope in protected]
    if spec.box_variant == 'gridfinity':
        from vault.gridfinity import GridfinityLayout
        grid = GridfinityLayout(spec)
        protected.append(('gridfinity_base', box_between(
            (grid.x_min, grid.y_min, grid.floor_z-.1),
            (grid.x_max, grid.y_max, grid.floor_z+grid.socket_height))))
    protected_checks = []
    for name, envelope in protected:
        amount = intersection_volume(removed, envelope)
        if added_volume > 1e-8:
            amount += intersection_volume(added, envelope)
        protected_checks.append({'feature': name, 'removed_mm3': amount,
                                 'passed': amount <= 1e-5})
    checks = {
        'valid': bool(patterned.is_valid),
        'one_solid': len(patterned.solids()) == 1,
        'one_shell': len(patterned.shells()) == 1,
        'unchanged_bounds': bounds_error < 1e-6,
        'additions_confined_to_cavity_backing': added_outside <= 1e-5,
        'changes_confined_to_wall_panels': outside_volume <= 1e-5,
        'positive_relief': volume(removed) > 1,
        'minimum_requested_web': (len(samples) >= (1 if spec.wall_pattern == 'plain' and spec.wall_perimeters is not None else 2)
                                 and all(item['minimum_passed'] for item in samples)
                                 and any(item['at_nominal_two_lines'] for item in samples)),
    }
    return {'specification': asdict(spec), 'checks': checks,
            'target_web_mm': wall_target_thickness(spec),
            'removed_volume_mm3': volume(removed), 'added_volume_mm3': added_volume,
            'outside_permitted_panel_mm3': outside_volume, 'bounds_error_mm': bounds_error,
            'minimum_web_mm': min((item['thickness_mm'] for item in samples), default=None),
            'normal_web_samples': samples, 'protected_features': protected_checks,
            'passed': all(checks.values()) and all(item['passed'] for item in protected_checks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', choices=('plain', 'waffle', 'miura'), default='miura')
    parser.add_argument('--family', choices=('S', 'M', 'L'), default='S')
    parser.add_argument('--depth-units', type=int, choices=range(3, 8), default=4)
    parser.add_argument('--height-units', type=int, choices=(1, 2), default=1)
    parser.add_argument('--box-floor', type=float, choices=(0., .8, 3.), default=.8)
    parser.add_argument('--box-variant', choices=('plain', 'gridfinity'), default='plain')
    parser.add_argument('--wall-perimeters', type=int, choices=(1, 2))
    parser.add_argument('--nozzle-size', type=float, choices=(.6, .8), default=.6)
    parser.add_argument('--baseline-step', type=Path)
    parser.add_argument('--pattern-step', type=Path)
    parser.add_argument('--output', type=Path, default=Path('out/reviews/box-wall-patterns.json'))
    args = parser.parse_args()
    spec = BoxSpec(args.family, args.depth_units, args.height_units, args.box_floor,
                   args.box_variant, box_rear_pattern=args.pattern, wall_pattern=args.pattern,
                   wall_perimeters=args.wall_perimeters, nozzle_size=args.nozzle_size)
    plain = import_step(args.baseline_step) if args.baseline_step else build_box(
        spec=replace(spec, box_rear_pattern='plain', wall_pattern='plain', wall_perimeters=None))
    patterned = import_step(args.pattern_step) if args.pattern_step else build_box(spec=spec)
    print(f'Auditing {spec.name}', flush=True)
    report = audit_box_rear_pattern(plain, patterned, spec)
    report['schema'] = 'vault-box-wall-pattern-audit/v1'
    report['inputs'] = {name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                        for name, path in (('baseline_step', args.baseline_step),
                                           ('pattern_step', args.pattern_step)) if path}
    report['limitations'] = ('Exact native removed-material containment and selected normal-thickness samples. '
        'Full-thickness structural lands and fold junctions remain. This does not certify slicer '
        'toolpaths, loaded strength, installation motion or physical printed fit.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"passed={report['passed']}; removed={report['removed_volume_mm3']:.3f} mm3; report={args.output}", flush=True)
    if not report['passed']:
        raise SystemExit('Box rear pattern audit failed')


if __name__ == '__main__':
    main()
