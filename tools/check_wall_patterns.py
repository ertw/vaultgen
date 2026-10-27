"""Check patterned modules against their plain native mechanical interfaces.

Run after sourcing .local-env. This is an exact removed-volume containment
audit plus explicit occupancy probes, not a print-strength qualification.
Optional STEP inputs permit checking the actual immutable exported solids.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

from build123d import Axis, Plane, Shape, Solid, Vector, import_step
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin

from vault.connectors import ConnectorParameters, build_connectors, build_connector_cutters
from vault.model import build_module
from vault.shell import ShellDimensions
from vault.spec import ModuleSpec
from vault.wall_patterns import apply_wall_pattern


TOLERANCE_MM3 = 1e-5


def volume(shape):
    return 0.0 if shape is None else sum(abs(solid.volume) for solid in shape.solids())


def intersection_volume(left, right):
    """One native common operation, avoiding Compound's per-child dispatch."""
    operation = BRepAlgoAPI_Common(left.wrapped, right.wrapped)
    if not operation.IsDone():
        raise RuntimeError('Pattern audit intersection failed')
    result = operation.Shape()
    return 0.0 if result.IsNull() else volume(Shape.cast(result))


def box_between(low, high):
    return Solid.make_box(*(b-a for a, b in zip(low, high)), Plane(origin=low))


def allowed_skin_volumes(spec, dimensions):
    """Independent envelope for changes: flat skins, lands, and stop collars.

    Connector root protection is checked separately against the actual native
    feature bounds. Recessed removal depth proves the remaining axis thickness;
    corrugated changes may occupy both original skin surfaces and additionally
    need the independent normal-thickness samples below.
    """
    d, h, w = dimensions, spec.height, spec.half_width
    rear = max(8.0, d.back_wall+3.0, d.rear_notch_depth+3.0)
    front = spec.depth-max(12.0, d.pocket_front_offset+d.pocket_length+3.0,
                           d.catch_front_offset+3.0)
    stop = spec.depth/2+d.stopper_center_offset
    stop_half = d.stopper_length/2+d.stopper_chamfer+.01+3.0
    corrugated = spec.pattern_construction == 'corrugated'
    side_depth = (d.channel_outer_inset if corrugated else spec.pattern_depth)+1e-7
    allowed = []
    for tier in spec.tier_offsets:
        z0 = max(d.envelope.corner_height+3.0, tier+d.channel_floor+3.0)
        z1 = min(h-d.envelope.corner_height-3.0, tier+d.channel_ceiling-3.0)
        for y0, y1 in ((rear, min(front, stop-stop_half)),
                       (max(rear, stop+stop_half), front)):
            if z1 <= z0 or y1 <= y0:
                continue
            allowed.extend((box_between((w-side_depth, y0, z0), (w+.01, y1, z1)),
                            box_between((-w-.01, y0, z0), (-w+side_depth, y1, z1))))
    if spec.pattern_faces == 'all':
        span = w-d.envelope.corner_width-3.0
        depth = (d.skin if corrugated else spec.pattern_depth)+1e-7
        for z0, z1 in ((-.01, depth), (h-depth, h+.01)):
            allowed.append(box_between((-span, rear, z0), (span, front, z1)))
    return allowed


def protected_feature_volumes(spec, dimensions, parameters):
    """Whole original connector footprints and all their underlying skin."""
    d = dimensions
    result = []
    for feature in [*build_connectors(spec, parameters), *build_connector_cutters(spec, parameters)]:
        bounds = feature.bounding_box()
        bottom = bounds.min.Z < 0
        z0, z1 = ((-6.0, d.skin+.01) if bottom
                  else (spec.height-d.skin-.01, spec.height+6.0))
        result.append((feature.label or 'shallow_track', box_between(
            (bounds.min.X-3.0, bounds.min.Y-3.0, z0),
            (bounds.max.X+3.0, bounds.max.Y+3.0, z1))))
    if spec.drawer_columns == 2:
        result.append(('divider', box_between(
            (-d.side_wall-3, 0, -.01), (d.side_wall+3, spec.depth, spec.height+.01))))
    return result


def protected_probes(spec, dimensions):
    """Material and clearance points at the unchanged working interfaces."""
    d, w, h, length = dimensions, spec.half_width, spec.height, spec.depth
    probes = []
    for side in (-1, 1):
        for tier in spec.tier_offsets:
            for y in (20.0, length/2, length-3.1):
                for z in (tier+d.channel_floor+.5, tier+23.5, tier+d.channel_ceiling-.5):
                    for offset in (-.04, .04):
                        feature = 'runner_back_panel' if z == tier+23.5 else 'runner_channel_land'
                        probes.append((feature, (side*(w-d.channel_outer_inset+offset), y, z)))
            cy, cz = length/2+d.stopper_center_offset, tier+d.stopper_center_z
            for dy, dz in ((0, 0), (0, d.stopper_height/2+.2),
                           (0, d.stopper_height/2+d.stopper_chamfer+.2),
                           (d.stopper_length/2+d.stopper_chamfer+.2, 0)):
                probes.append(('stopper', (side*(w-.2), cy+dy, cz+dz)))
            bore_x = side*(w-d.bore_inset)
            for z in (tier+d.bore_lower_z, tier+d.bore_upper_z):
                probes.extend((('bore_clearance', (bore_x, 20, z)),
                               ('bore_wall', (bore_x, 20, z+d.bore_radius+.1))))
            for y in (length-.2, length-3.1):
                probes.append(('front_lip', (side*(w-.1), y, tier+23.5)))
    for y in (20.0, length/2, length-8.0):
        for z in (d.skin-.04, d.skin+.04, h-d.skin-.04, h-d.skin+.04):
            probes.append(('inner_skin', (0, y, z)))
    for side, z in ((-1, 8.2), (1, 38.8)):
        for tier in spec.tier_offsets:
            probes.append(('mouth_support', (side*(w-12.4), length-3.1, z+tier)))
    probes.extend((('rear_wall', (0, d.back_wall-.04, 23.5)),
                   ('rear_clearance', (0, d.back_wall+.04, 23.5))))
    return probes


def normal_web_samples(patterned, spec, dimensions, limit_per_face=6):
    """Measure actual native material intervals along patterned face normals.

    UV midpoints outside a trimmed face are rejected. Different normal
    directions cover valleys and slopes; this remains a sampled check.
    """
    allowed = [item.bounding_box() for item in allowed_skin_volumes(spec, dimensions)]
    directions = {'left': Vector(-1, 0, 0), 'right': Vector(1, 0, 0)}
    if spec.pattern_faces == 'all':
        directions.update(top=Vector(0, 0, 1), bottom=Vector(0, 0, -1))
    counts, seen, samples = {name: 0 for name in directions}, set(), []
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(patterned.wrapped, 1e-6)
    for face in sorted(patterned.faces(), key=lambda item: item.area, reverse=True):
        if all(count >= limit_per_face for count in counts.values()):
            break
        point = face.position_at(.5, .5)
        if not any(all(a-1e-6 <= p <= b+1e-6 for a, p, b in zip(bounds.min, point, bounds.max))
                   for bounds in allowed):
            continue
        if face.distance_to(point) > 1e-6:
            continue
        normal = face.normal_at(point)
        for name, direction in directions.items():
            if counts[name] >= limit_per_face or normal.dot(direction) < .1:
                continue
            depth = {'left': point.X+spec.half_width, 'right': spec.half_width-point.X,
                     'top': spec.height-point.Z, 'bottom': point.Z}[name]
            if not 1e-5 < depth <= spec.pattern_depth+1e-6:
                continue
            key = (name, *(round(component, 2) for component in normal))
            if key in seen:
                continue
            seen.add(key)
            start = point+normal*.01
            intersector.Perform(gp_Lin(Axis(start, -normal).wrapped), 0.,
                                3*max(dimensions.skin, dimensions.channel_outer_inset))
            if not intersector.IsDone():
                continue
            distances = sorted(intersector.WParameter(index) for index in range(1, intersector.NbPnt()+1))
            distinct = []
            for distance in distances:
                if not distinct or distance-distinct[-1] > 1e-5:
                    distinct.append(distance)
            if len(distinct) < 2 or abs(distinct[0]-.01) > 1e-4:
                continue
            thickness = distinct[1]-distinct[0]
            samples.append({'face': name, 'point_mm': tuple(point), 'normal': tuple(normal),
                            'thickness_mm': thickness,
                            'minimum_passed': thickness >= 2*spec.pattern_line_width-.01,
                            'at_nominal_two_lines': abs(thickness-2*spec.pattern_line_width) <= .02})
            counts[name] += 1
    return samples


def audit_pattern(plain, patterned, spec, dimensions=None, parameters=None):
    dimensions = dimensions or ShellDimensions(back_wall=spec.module_rear)
    parameters = parameters or ConnectorParameters()
    removed = plain.cut(patterned)
    added_volume = volume(patterned.cut(plain))
    outside_volume = volume(removed.cut(*allowed_skin_volumes(spec, dimensions)))
    roots = []
    for name, protected in protected_feature_volumes(spec, dimensions, parameters):
        overlap = intersection_volume(removed, protected)
        roots.append({'feature': name, 'removed_mm3': overlap, 'passed': overlap <= TOLERANCE_MM3})
    probes = []
    for feature, point in protected_probes(spec, dimensions):
        if (spec.pattern_construction == 'corrugated'
                and feature in ('inner_skin', 'runner_back_panel')
                and point[1] < spec.depth-12):
            continue
        before, after = bool(plain.is_inside(point)), bool(patterned.is_inside(point))
        probes.append({'feature': feature, 'point_mm': point, 'plain_material': before,
                       'patterned_material': after, 'passed': before == after})
    bounds_error = max(abs(a-b) for end in ('min', 'max') for a, b in zip(
        getattr(plain.bounding_box(), end), getattr(patterned.bounding_box(), end)))
    minimum = min(dimensions.skin, dimensions.channel_outer_inset) if spec.pattern_faces == 'all' else dimensions.channel_outer_inset
    w, h, length = spec.half_width, spec.height, spec.depth
    face_boxes = {
        'left': box_between((-w-.01, 0, 0), (-w+dimensions.channel_outer_inset, length, h)),
        'right': box_between((w-dimensions.channel_outer_inset, 0, 0), (w+.01, length, h)),
    }
    if spec.pattern_faces == 'all':
        face_boxes.update(bottom=box_between((-w, 0, -.01), (w, length, dimensions.skin)),
                          top=box_between((-w, 0, h-dimensions.skin), (w, length, h+.01)))
    face_removals = {name: intersection_volume(removed, bounds) for name, bounds in face_boxes.items()}
    samples = normal_web_samples(patterned, spec, dimensions) if spec.pattern_construction == 'corrugated' else []
    minimum_web = min((sample['thickness_mm'] for sample in samples), default=minimum-spec.pattern_depth)
    web_passed = (bool(samples) and all(sample['minimum_passed'] for sample in samples)
                  and all(any(sample['face'] == face and sample['at_nominal_two_lines'] for sample in samples)
                          for face in face_boxes)) if spec.pattern_construction == 'corrugated' else minimum_web >= 2*spec.pattern_line_width-1e-8
    checks = {'valid': bool(patterned.is_valid), 'one_solid': len(patterned.solids()) == 1,
              'one_shell': len(patterned.shells()) == 1,
              'unchanged_bounds': bounds_error < 1e-6,
              'only_removes_material': added_volume <= TOLERANCE_MM3,
              'changes_confined_to_permitted_skins': outside_volume <= TOLERANCE_MM3,
              'positive_relief': volume(removed) > 1,
              'all_requested_faces_have_relief': all(amount > 1 for amount in face_removals.values()),
              'minimum_two_line_web': web_passed}
    return {'specification': asdict(spec), 'checks': checks,
            'added_volume_mm3': added_volume, 'removed_volume_mm3': volume(removed),
            'outside_permitted_skins_mm3': outside_volume, 'bounds_error_mm': bounds_error,
            'removed_by_face_mm3': face_removals,
            'minimum_web_mm': minimum_web, 'normal_web_samples': samples,
            'protected_roots': roots, 'probes': probes,
            'passed': all(checks.values()) and all(item['passed'] for item in roots+probes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', choices=('waffle', 'miura'), default='waffle')
    parser.add_argument('--family', choices=('S', 'M', 'L'), default='S')
    parser.add_argument('--depth-units', type=int, default=4)
    parser.add_argument('--height-units', type=int, choices=(1, 2), default=1)
    parser.add_argument('--drawer-columns', type=int, choices=(1, 2), default=1)
    parser.add_argument('--faces', choices=('all', 'sides'), default='all')
    parser.add_argument('--construction', choices=('recessed', 'corrugated'), default='recessed')
    parser.add_argument('--pattern-pitch', type=float, default=14.0)
    parser.add_argument('--pattern-depth', type=float, default=1.7)
    parser.add_argument('--pattern-line-width', type=float, default=.65)
    parser.add_argument('--module-rear', type=float, choices=(.9, 2.0), default=.9)
    parser.add_argument('--baseline-step', type=Path)
    parser.add_argument('--pattern-step', type=Path)
    parser.add_argument('--output', type=Path, default=Path('out/reviews/wall-patterns.json'))
    args = parser.parse_args()
    spec = ModuleSpec(args.family, args.depth_units, args.height_units,
                      drawer_columns=args.drawer_columns, wall_pattern=args.pattern, pattern_faces=args.faces,
                      pattern_construction=args.construction, pattern_pitch=args.pattern_pitch,
                      pattern_depth=args.pattern_depth, pattern_line_width=args.pattern_line_width,
                      module_rear=args.module_rear)
    plain = import_step(args.baseline_step) if args.baseline_step else build_module(replace(spec, wall_pattern='plain'))
    patterned = (import_step(args.pattern_step) if args.pattern_step else
                 apply_wall_pattern(plain, spec, ShellDimensions(back_wall=spec.module_rear), ConnectorParameters()))
    print(f'Auditing {spec.name}', flush=True)
    report = audit_pattern(plain, patterned, spec)
    report['schema'] = 'vault-wall-pattern-interface-audit/v1'
    report['inputs'] = {name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                        for name, path in (('baseline_step', args.baseline_step), ('pattern_step', args.pattern_step)) if path}
    report['limitations'] = ('Native geometric containment, protected-root volume and selected occupancy checks. '
        'Recessed relief leaves two-line minimum valleys with thicker slopes. Corrugated web thickness '
        'uses selected native face-normal samples; protected lands and transitions remain thicker. '
        'Does not certify slicer toolpaths, loaded strength, installation motion or printed fit.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"passed={report['passed']}; removed={report['removed_volume_mm3']:.3f} mm3; report={args.output}", flush=True)
    if not report['passed']:
        raise SystemExit('Pattern interface audit failed')


if __name__ == '__main__':
    main()
