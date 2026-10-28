"""Check removable drawer-fit containers against the selected plain drawer.

The planning cells are anisotropic and are not Gridfinity sockets. This audit
uses native drawer solids, the plain cavity registration, measured wall faces,
and layers through actual divider junctions. It does not certify printed fit,
slicer paths, stiffness under load, or removal motion.
"""
import argparse
import hashlib
import json
from pathlib import Path

from build123d import Axis, CenterOf, Plane, Shape, Solid, import_step
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin

from vault.bin import build_bins
from vault.bin_config import BinConfiguration, bin_layout
from vault.box import BoxSpec, build_box
if __package__:
    from .check_gridfinity_bins import intersection_volume, load_build_parts
else:
    from check_gridfinity_bins import intersection_volume, load_build_parts


TOLERANCE = 1e-5


def normal_wall_samples(part, config, limit=32):
    """Measure opposing faces above this container's actual 1.2 mm floor."""
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(part.wrapped, 1e-6)
    samples, normals = [], set()
    for face in sorted(part.faces(), key=lambda item: item.area, reverse=True):
        point = face.center(CenterOf.MASS)
        if (not config.floor_top_mm+.15 < point.Z < config.height_mm-.15
                or face.distance_to(point) > 1e-6):
            continue
        normal = face.normal_at(point)
        if config.wall_pattern == 'miura':
            if not .01 < abs(normal.Z) < .3:
                continue
        elif abs(normal.Z) > 1e-6 or max(abs(normal.X),abs(normal.Y)) < .99:
            continue
        key = tuple(round(value, 3) for value in normal)
        if key in normals:
            continue
        intersector.Perform(gp_Lin(Axis(point+normal*.01, -normal).wrapped), 0., 4.)
        if not intersector.IsDone():
            continue
        distinct = []
        for distance in sorted(intersector.WParameter(i)
                               for i in range(1, intersector.NbPnt()+1)):
            if not distinct or distance-distinct[-1] > 1e-5:
                distinct.append(distance)
        if len(distinct) < 2 or abs(distinct[0]-.01) > 1e-4:
            continue
        thickness = distinct[1]-distinct[0]
        normals.add(key)
        samples.append({'point_mm': list(point), 'normal': list(normal),
                        'thickness_mm': thickness,
                        'passed': abs(thickness-config.wall_thickness_mm) < .02})
        if len(samples) >= limit:
            break
    return samples


def junction_layer_samples(part, config, cells):
    """Require one connected layer at real T/X joins on the stretched grid."""
    selected, arms, divider_vertices = set(cells), {}, set()

    def add_edge(a, b):
        arms.setdefault(a, set()).add(b)
        arms.setdefault(b, set()).add(a)

    for x, y in cells:
        for neighbor, a, b in (
                ((x-1,y), (x,y), (x,y+1)), ((x+1,y), (x+1,y), (x+1,y+1)),
                ((x,y-1), (x,y), (x+1,y)), ((x,y+1), (x,y+1), (x+1,y+1))):
            if neighbor not in selected:
                add_edge(a, b)
    for divider in config.dividers:
        if divider.adjacent_cells()[0] not in selected:
            continue
        a = (divider.x, divider.y)
        b = (divider.x+(divider.axis == 'y'), divider.y+(divider.axis == 'x'))
        add_edge(a, b)
        divider_vertices.update((a, b))
    samples = []
    height = config.height_mm-config.floor_top_mm
    for x, y in sorted(divider_vertices):
        if len(arms[(x,y)]) < 3:
            continue
        px, py = x*config.pitch_x_mm, y*config.pitch_y_mm
        for fraction in (.11, .47, .89):
            z = config.floor_top_mm+height*fraction
            region = Solid.make_box(16., 16., .002,
                                    Plane(origin=(px-8., py-8., z-.001)))
            operation = BRepAlgoAPI_Common(part.wrapped, region.wrapped)
            if not operation.IsDone():
                raise RuntimeError('Drawer-bin junction layer intersection failed')
            shape = operation.Shape()
            count = 0 if shape.IsNull() else len(Shape.cast(shape).solids())
            samples.append({'junction_mm': [px, py], 'z_mm': z,
                            'connected_regions': count, 'passed': count == 1})
    return samples


def audit_drawer_bins(config, parts, drawer=None):
    if config.container_type != 'drawer':
        raise ValueError('Expected drawer-fit container configuration')
    spec = BoxSpec(config.family, config.depth_units, config.height_units,
                   config.drawer_floor, 'plain')
    drawer = build_box(spec=spec, include_supports=False) if drawer is None else drawer
    translation = (-config.width_mm/2, 5.3, 5+config.drawer_floor+.25)
    mounted = {name: part.translate(translation) for name, part in parts.items()}
    collisions = {name: intersection_volume(drawer, part)
                  for name, part in mounted.items()}
    items = list(parts.items())
    pairs = [{'parts': [name, other], 'volume_mm3': intersection_volume(left, right)}
             for i, (name, left) in enumerate(items) for other, right in items[i+1:]]
    rim_z = drawer.bounding_box().max.Z
    clearance = min(rim_z-part.bounding_box().max.Z for part in mounted.values())
    # A partial drawing may not reach the side. Move its rightmost component
    # through the remaining unpainted cells, then 1 mm past its fitted position.
    rightmost_name, rightmost = max(parts.items(), key=lambda item: item[1].bounding_box().max.X)
    shift = 1.+max(0., config.width_mm-.25-rightmost.bounding_box().max.X)
    shifted = intersection_volume(drawer, mounted[rightmost_name].translate((shift, 0, 0)))
    lowered = intersection_volume(drawer, next(iter(mounted.values())).translate((0, 0, -.8)))
    checks, samples, layers = [], [], []
    for (name, part), cells in zip(items, config.components):
        selected = set(cells)
        floor_z = config.floor_top_mm-.1
        cavity_z = config.floor_top_mm+(config.height_mm-config.floor_top_mm)*.47
        centers = lambda group, z: [((x+.5)*config.pitch_x_mm,
                                     (y+.5)*config.pitch_y_mm, z) for x, y in group]
        floor = all(part.is_inside(point) for point in centers(cells, floor_z))
        cavity = all(not part.is_inside(point) for point in centers(cells, cavity_z))
        missing = [(x,y) for y in range(config.rows) for x in range(config.columns)
                   if (x,y) not in selected]
        missing_open = all(not part.is_inside(point) for z in (floor_z, cavity_z)
                           for point in centers(missing, z))
        junctions = [(x+1,y+1) for x,y in cells
                     if {(x+1,y), (x,y+1), (x+1,y+1)} <= selected]
        floor = floor and all(part.is_inside((x*config.pitch_x_mm, y*config.pitch_y_mm, floor_z))
                                  for x,y in junctions)
        divider_ends = {point for divider in config.dividers for point in (
            (divider.x, divider.y),
            (divider.x+(divider.axis == 'y'), divider.y+(divider.axis == 'x')))}
        cavity = cavity and all(not part.is_inside((x*config.pitch_x_mm, y*config.pitch_y_mm, cavity_z))
                                for x,y in junctions if (x,y) not in divider_ends)
        bounds = part.bounding_box()
        checks.append({'part': name,
                       'valid_solid_and_shell': bool(part.is_valid and len(part.solids()) == 1
                                                     and len(part.shells()) == 1),
                       'selected_floor': floor, 'open_compartments': cavity,
                       'missing_cells_open': missing_open,
                       'footless_bottom': abs(bounds.min.Z) < 1e-6,
                       'height': abs(bounds.max.Z-config.height_mm) < 1e-6})
        samples.extend({'part': name, **sample} for sample in normal_wall_samples(part, config))
        layers.extend({'part': name, **sample} for sample in junction_layer_samples(part, config, cells))
    passed = (len(parts) == len(config.components)
              and all(all(value for key, value in check.items() if key != 'part') for check in checks)
              and all(value < TOLERANCE for value in collisions.values())
              and all(pair['volume_mm3'] < TOLERANCE for pair in pairs)
              and clearance >= 1.-1e-6 and shifted > .1 and lowered > .1
              and bool(samples) and all(sample['passed'] for sample in samples)
              and all(sample['passed'] for sample in layers))
    return {'passed': passed, 'configuration': config.as_dict(), 'layout': bin_layout(config),
            'native_to_drawer_translation_mm': list(translation),
            'drawer_collisions_mm3': collisions, 'between_bin_collisions': pairs,
            'rim_clearance_mm': clearance, 'positive_control_shift_x_mm': shift,
            'shifted_collision_mm3': shifted, 'lowered_collision_mm3': lowered,
            'container_checks': checks, 'normal_wall_samples': samples,
            'junction_layer_samples': layers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', type=Path)
    parser.add_argument('--build', type=Path,
                        help='Checked build; restore print STEPs using recorded native transforms')
    parser.add_argument('--case', default='S4:1', help='Supported family/depth:height, such as M5:2')
    parser.add_argument('--wall-pattern', choices=('plain', 'miura'), default='miura')
    parser.add_argument('--wall-perimeters', type=int, choices=(1,2), default=2)
    parser.add_argument('--drawer-floor', type=float, choices=(.8,3.), default=.8)
    parser.add_argument('--step', action='append', type=Path,
                        help='One native-coordinate STEP per connected component')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    evidence = None
    if args.build:
        if args.configuration or args.step:
            parser.error('--build supplies its own configuration and recorded print STEPs')
        config, parts, evidence = load_build_parts(args.build)
    elif args.configuration:
        config = BinConfiguration.parse(json.loads(args.configuration.read_text()))
    else:
        try:
            size, height = args.case.split(':')
            config = BinConfiguration(container_type='drawer', family=size[0].upper(),
                depth_units=int(size[1:]), height_units=int(height), drawer_floor=args.drawer_floor,
                wall_pattern=args.wall_pattern, wall_perimeters=args.wall_perimeters)
        except (ValueError, IndexError):
            parser.error('Use a supported case such as S4:1 or M5:2')
    if config.container_type != 'drawer':
        parser.error('The configuration must select the drawer-fit container type')
    if args.step:
        if len(args.step) != len(config.components):
            parser.error('Provide one native STEP per connected component')
        parts = {f'bin_{i:02d}': import_step(path) for i, path in enumerate(args.step, 1)}
    elif not args.build:
        parts = build_bins(config)
    report = {'schema': 'vault-drawer-bin-fit/v1', **audit_drawer_bins(config, parts),
              'limitations': 'Stationary CAD fit, sampled wall thickness and junction continuity only; '
                             'not slicer paths, printed fit, loaded stiffness or removal motion.'}
    if args.step:
        report['step_inputs'] = [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                                 for path in args.step]
    if evidence:
        report.update(evidence)
    output = json.dumps(report, indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output, end='')
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
