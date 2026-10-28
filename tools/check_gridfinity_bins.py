"""Check native editable bins against the actual native Gridfinity drawer.

Uses recorded Gridfinity datums, exact solid collisions, independent floor and
compartment probes, sampled normal wall thickness and junction layer continuity. This cannot certify
slicer perimeter placement, printed fit, loaded stiffness, or removal motion.
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
from vault.assembly import apply_transform
from vault.box import BoxSpec, build_box
from vault.gridfinity import GridfinityLayout


TOLERANCE = 1e-5


def intersection_volume(left, right):
    operation = BRepAlgoAPI_Common(left.wrapped, right.wrapped)
    if not operation.IsDone():
        raise RuntimeError('Bin interface intersection failed')
    shape = operation.Shape()
    return 0. if shape.IsNull() else sum(abs(s.volume) for s in Shape.cast(shape).solids())


def junction_layer_samples(part, config, cells):
    """Require connected material at real T/X joins, independently of the floor.

    A free-ended divider need not touch a boundary. Restrict these checks to
    vertices where a painted divider actually meets at least two other arms;
    do not mistake its projection onto a remote wall for an attachment.
    """
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
    height = config.height_mm-7.
    for x, y in sorted(divider_vertices):
        if len(arms[(x,y)]) < 3:
            continue
        for fraction in (.11, .47, .89):
            z = 7.+height*fraction
            region = Solid.make_box(16.,16.,.002,
                Plane(origin=(x*42.-8.,y*42.-8.,z-.001)))
            operation = BRepAlgoAPI_Common(part.wrapped, region.wrapped)
            if not operation.IsDone():
                raise RuntimeError('Bin junction layer intersection failed')
            shape = operation.Shape()
            count = 0 if shape.IsNull() else len(Shape.cast(shape).solids())
            samples.append({'junction_mm':[x*42.,y*42.], 'z_mm':z,
                            'connected_regions':count, 'passed':count == 1})
    return samples


def load_build_parts(directory):
    """Restore checked print STEPs using their recorded print-to-native frames."""
    directory = Path(directory)
    manifest_path = directory/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get('passed') or manifest.get('schema') != 'cad-build-v1':
        raise ValueError('Expected a completed checked build')
    checksums = manifest.get('checksums', {})

    def verified_path(relative):
        path = directory/relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != checksums.get(relative):
            raise ValueError(f'Build checksum mismatch: {relative}')
        return path, digest

    metadata_path, metadata_hash = verified_path('build.json')
    metadata = json.loads(metadata_path.read_text())
    config = BinConfiguration.parse(metadata['gridfinity_configuration'])
    if config.key != manifest['configuration_hash']:
        raise ValueError('Build configuration identity mismatch')
    parts, inputs = {}, []
    expected = [f'bin_{index:02d}' for index in range(1,len(config.components)+1)]
    if set(metadata['parts']) != set(expected):
        raise ValueError('Build components do not match the recorded grid drawing')
    for name in expected:
        part = metadata['parts'][name]
        assembly = part['assembly_mesh']
        transform = assembly['print_to_native']
        if part['kind'] != 'gridfinity_bins' or assembly['coordinates'] != 'native' or len(transform) != 16:
            raise ValueError(f'Invalid Gridfinity placement metadata: {name}')
        path, digest = verified_path(f'{name}_print.step')
        parts[name] = apply_transform(import_step(path), transform)
        inputs.append({'part':name, 'path':str(path), 'sha256':digest,
                       'print_to_native':transform})
    evidence = {'build_id':manifest['build_id'], 'source_hash':manifest['source_hash'],
                'configuration_hash':manifest['configuration_hash'],
                'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                'build_metadata_sha256':metadata_hash, 'step_inputs':inputs}
    return config, parts, evidence


def normal_wall_samples(part, config, limit=16):
    """Inspect actual opposing native faces, rather than configured thickness."""
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(part.wrapped, 1e-6)
    samples, normals = [], set()
    for face in sorted(part.faces(), key=lambda item: item.area, reverse=True):
        # The UV midpoint of a triangular blend face can lie on a fold edge.
        # Its area centroid measures the facet interior instead of that crease.
        point = face.center(CenterOf.MASS)
        if not 8.1 < point.Z < config.height_mm-1.1 or face.distance_to(point) > 1e-6:
            continue
        normal = face.normal_at(point)
        if config.wall_pattern == 'miura':
            if not .01 < abs(normal.Z) < .3:
                continue
        elif abs(normal.Z) > 1e-6 or max(abs(normal.X),abs(normal.Y)) < .99:
            continue
        key = tuple(round(value,3) for value in normal)
        if key in normals:
            continue
        intersector.Perform(gp_Lin(Axis(point+normal*.01,-normal).wrapped),0.,4.)
        if not intersector.IsDone():
            continue
        distances = sorted(intersector.WParameter(i) for i in range(1,intersector.NbPnt()+1))
        distinct = []
        for distance in distances:
            if not distinct or distance-distinct[-1] > 1e-5:
                distinct.append(distance)
        if len(distinct) < 2 or abs(distinct[0]-.01) > 1e-4:
            continue
        thickness = distinct[1]-distinct[0]
        normals.add(key)
        samples.append({'point_mm': list(point), 'normal': list(normal), 'thickness_mm': thickness,
                        'passed': abs(thickness-config.wall_thickness_mm) < .02})
        if len(samples) >= limit:
            break
    return samples


def audit_gridfinity_bins(config, parts, box_floor=3., drawer=None):
    spec = BoxSpec(config.family,config.depth_units,config.height_units,box_floor,'gridfinity')
    layout = GridfinityLayout(spec)
    drawer = build_box(spec=spec,include_supports=False) if drawer is None else drawer
    # The nominal bridge at Z4.75 rests on webs at floor_z+5. All components
    # keep cell registration; their feet therefore start .25 above floor_z.
    translation = (layout.x_min,layout.y_min,layout.floor_z+.25)
    mounted = {name: part.translate(translation) for name,part in parts.items()}
    collisions = {name: intersection_volume(drawer,part) for name,part in mounted.items()}
    pair_collisions = []
    items = list(parts.items())
    for i,(name,left) in enumerate(items):
        for other,right in items[i+1:]:
            pair_collisions.append({'parts': [name,other], 'volume_mm3': intersection_volume(left,right)})
    rim_z = drawer.bounding_box().max.Z
    top_clearance = min(rim_z-part.bounding_box().max.Z for part in mounted.values())
    first = next(iter(mounted.values()))
    shifted = intersection_volume(drawer,first.translate((1.,0,0)))
    lowered = intersection_volume(drawer,first.translate((0,0,-.35)))
    checks, samples, layers = [], [], []
    for (name,part),cells in zip(items,config.components):
        valid = bool(part.is_valid and len(part.solids()) == 1 and len(part.shells()) == 1)
        floor = all(part.is_inside(((x+.5)*42,(y+.5)*42,6.9)) for x,y in cells)
        cavity = all(not part.is_inside(((x+.5)*42,(y+.5)*42,8.)) for x,y in cells)
        selected = set(cells)
        junctions = [(x+1,y+1) for x,y in cells if {(x+1,y),(x,y+1),(x+1,y+1)} <= selected]
        floor = floor and all(part.is_inside((x*42,y*42,6.9)) for x,y in junctions)
        divider_ends = set()
        for divider in config.dividers:
            divider_ends.add((divider.x,divider.y))
            divider_ends.add((divider.x+(divider.axis=='y'),divider.y+(divider.axis=='x')))
        cavity = cavity and all(not part.is_inside((x*42,y*42,15.))
                                for x,y in junctions if (x,y) not in divider_ends)
        height = abs(part.bounding_box().max.Z-config.height_mm) < 1e-6
        checks.append({'part':name,'valid_solid_and_shell':valid,'floor':floor,'cavity':cavity,'height':height})
        samples.extend({'part':name,**sample} for sample in normal_wall_samples(part,config))
        layers.extend({'part':name,**sample} for sample in junction_layer_samples(part,config,cells))
    passed = (len(parts) == len(config.components) and all(all(v for k,v in check.items() if k != 'part') for check in checks)
              and all(value < TOLERANCE for value in collisions.values())
              and all(item['volume_mm3'] < TOLERANCE for item in pair_collisions)
              and top_clearance > 1 and shifted > .1 and lowered > .1
              and bool(samples) and all(sample['passed'] for sample in samples)
              and all(sample['passed'] for sample in layers))
    return {'passed':passed,'configuration':config.as_dict(),'layout':bin_layout(config),
            'box_floor_mm':box_floor,'native_to_drawer_translation_mm':list(translation),
            'drawer_collisions_mm3':collisions,'between_bin_collisions':pair_collisions,
            'rim_clearance_mm':top_clearance,'shifted_collision_mm3':shifted,'lowered_collision_mm3':lowered,
            'container_checks':checks,'normal_wall_samples':samples,'junction_layer_samples':layers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', type=Path)
    parser.add_argument('--build', type=Path,
                        help='Checked build directory; audit print STEPs using recorded native transforms')
    parser.add_argument('--case', default='S3:1', help='Drawer family/depth:height, such as L7:2')
    parser.add_argument('--wall-pattern', choices=('plain','miura'), default='plain')
    parser.add_argument('--wall-perimeters', type=int, choices=(1,2), default=2)
    parser.add_argument('--box-floor', type=float, choices=(0.,.8,3.), default=3.)
    parser.add_argument('--step', action='append', type=Path, help='One native-coordinate STEP per connected component, in component order')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    evidence = None
    if args.build:
        if args.configuration or args.step:
            parser.error('--build supplies its own configuration and recorded print STEP files')
        config, parts, evidence = load_build_parts(args.build)
    elif args.configuration:
        config = BinConfiguration.parse(json.loads(args.configuration.read_text()))
    else:
        try:
            size,height = args.case.split(':')
            config = BinConfiguration(family=size[0].upper(),depth_units=int(size[1:]),height_units=int(height),
                                      wall_pattern=args.wall_pattern,wall_perimeters=args.wall_perimeters)
        except (ValueError,IndexError):
            parser.error('Use a supported drawer case such as S3:1 or L7:2')
    if args.step:
        if len(args.step) != len(config.components):
            parser.error('Provide one STEP file per connected component')
        parts = {f'bin_{i:02d}':import_step(path) for i,path in enumerate(args.step,1)}
    elif not args.build:
        parts = build_bins(config)
    report = {'schema':'vault-gridfinity-bin-fit/v1',**audit_gridfinity_bins(config,parts,args.box_floor),
              'limitations':'Nominal stationary CAD fit, sampled wall thickness and junction layer continuity only; not slicer paths, printed fit, loaded stiffness or removal motion.'}
    if args.step:
        report['step_inputs'] = [{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path in args.step]
    if evidence:
        report.update(evidence)
    output = json.dumps(report,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(output)
    print(output,end='')
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
