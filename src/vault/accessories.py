"""Universal native accessories; reference meshes are never constructor inputs.

Coordinates are the supplied flat print orientation, in millimetres. Small
source blends are regularized; these are reconstructed, untested printed fits.
"""
from dataclasses import dataclass
from math import isfinite

from build123d import Axis, Edge, Face, Kind, Plane, Solid, Wire

ACCESSORIES = {'key': 'Snap-fit key', 'spring': 'Spring',
               'runner_stop': 'Runner stop', 'facade_cap': 'Facade cap', 'key_cap': 'Key cap', 'latch': 'Latch'}


@dataclass(frozen=True)
class AccessorySpec:
    accessory: str

    def __post_init__(self):
        if self.accessory not in ACCESSORIES:
            raise ValueError('Unknown accessory')

    @property
    def slug(self):
        return 'snap_key' if self.accessory == 'key' else self.accessory

    @property
    def name(self):
        return ACCESSORIES[self.accessory]


@dataclass(frozen=True)
class SpringDimensions:
    # Retreat every outline edge, including the flexure and seating fork.
    edge_clearance: float = 0.0
    thickness_clearance: float = 0.0

    def __post_init__(self):
        for value in (self.edge_clearance, self.thickness_clearance):
            if not isfinite(value) or not 0 <= value <= .25:
                raise ValueError('Spring allowances must be between 0 and 0.25 mm')


def one(shape):
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError("Accessory must be connected")
        shape = shape[0]
    if not shape.is_valid or len(shape.solids()) != 1 or len(shape.shells()) != 1:
        raise ValueError('Accessory must be one valid solid with one boundary shell')
    return shape.solids()[0]


def capsule(radius, center, z=0, vertical=False):
    def p(x,y):
        return (-y,x,z) if vertical else (x,y,z)
    return Wire([Edge.make_line(p(-center,-radius),p(center,-radius)),
                 Edge.make_three_point_arc(p(center,-radius),p(center+radius,0),p(center,radius)),
                 Edge.make_line(p(center,radius),p(-center,radius)),
                 Edge.make_three_point_arc(p(-center,radius),p(-center-radius,0),p(-center,-radius))])


def extrude(wire, height):
    return Solid.extrude(Face(wire), (0,0,height))


def build_facade_cap():
    # 9.84 mm skirt in the facade's 10 mm counterbore; closed face down.
    outer = Solid.make_cylinder(4.92,3.8)
    outer = outer.chamfer(.3,None,outer.edges())
    return one(outer.cut(Solid.make_cylinder(3.92,2.8,Plane(origin=(0,0,1.0)))))


def build_key_cap():
    # Capsule socket retains the measured end centers, wall and retention groove.
    body = extrude(capsule(6.586,12.313),11.673)
    rim_edges = [e for e in body.edges() if abs(e.center().Z)<1e-6 or abs(e.center().Z-11.673)<1e-6]
    body = body.fillet(2.3,rim_edges)
    socket = extrude(capsule(4.59,9.3135,2.0),11)
    groove = Solid.make_loft([capsule(r,9.3135,z) for z,r in
                             [(7.2,4.59),(7.5,4.89),(8.1,4.89),(8.4,4.59)]],ruled=True)
    body = body.cut(socket.fuse(groove))
    # Small orientation dimple in the closed face (not a through hole).
    dimple = Solid.make_sphere(4,Plane(origin=(-12.3,0,-2.5)))
    return one(body.cut(dimple))


def build_runner_stop():
    # Capsule flange and split, mildly tapered snap stem.
    body = Solid.make_loft([capsule(r,5.1,z,True) for z,r in
                           [(0,3.677),(.2,3.877),(.3,3.85),(1.002,3.16),
                            (7.68,3.553),(8.188,3.053)]],ruled=True)
    # Native arcs reproduce the circular snap relief; a narrow slot tip leaves
    # a continuous flange. No sampled section is consumed by this constructor.
    edges=[]
    def p(x,z): return (x,-10,z)
    def line(a,b): edges.append(Edge.make_line(p(*a),p(*b)))
    def arc(a,m,b): edges.append(Edge.make_three_point_arc(p(*a),p(*m),p(*b)))
    line((-.015,1.002),(.015,1.002))
    line((.015,1.002),(.146,2.038))
    arc((.146,2.038),(.227,2.32),(.388,2.57))
    arc((.388,2.57),(.87,3.393),(.545,4.181))
    arc((.545,4.181),(.48,4.37),(.479,4.57))
    line((.479,4.57),(.96,8.3));line((.96,8.3),(-.96,8.3))
    line((-.96,8.3),(-.479,4.57))
    arc((-.479,4.57),(-.48,4.37),(-.545,4.181))
    arc((-.545,4.181),(-.87,3.393),(-.388,2.57))
    arc((-.388,2.57),(-.227,2.32),(-.146,2.038))
    line((-.146,2.038),(-.015,1.002))
    cutter=Solid.extrude(Face(Wire(edges)),(0,20,0))
    return one(body.cut(cutter))


def build_spring(dimensions=None):
    d=dimensions or SpringDimensions()
    # Alternating R5/R1.125 turns keep the measured flexure pitch and throat.
    edges=[]; current=(-22.292,-2.5)
    def line(end):
        nonlocal current
        edges.append(Edge.make_line((*current,0),(*end,0)));current=end
    def arc(mid,end):
        nonlocal current
        edges.append(Edge.make_three_point_arc((*current,0),(*mid,0),(*end,0)));current=end
    arc((-23.737,0),(-22.292,2.32));line((-22.292,8.75))
    arc((-21.47,9.55),(-20.65,8.75));line((-18.417,-13))
    arc((-17.292,-14.125),(-16.167,-13));line((-16.167,13))
    arc((-11.167,18),(-6.167,13));line((-6.167,-13))
    arc((-5.042,-14.125),(-3.917,-13));line((-3.917,13))
    arc((1.083,18),(6.083,13));line((6.083,-13))
    arc((7.683,-14.6),(9.283,-13));line((9.283,-7.275))
    arc((9.58,-6.57),(10.6,-6.325))
    arc((19.9,0),(10.6,6.325));arc((9.58,6.57),(9.283,7.275))
    line((9.283,15.5));arc((10.162,17.621),(12.283,18.5))
    line((20.737,18.5));arc((22.858,17.621),(23.737,15.5))
    line((23.737,-15.5));arc((22.858,-17.621),(20.737,-18.5))
    line((7.208,-18.5));arc((3.672,-17.036),(2.208,-13.5))
    line((2.208,13));arc((1.083,14.125),(-.042,13));line((-.042,-13))
    arc((-5.042,-18),(-10.042,-13));line((-10.042,13))
    arc((-11.167,14.125),(-12.292,13));line((-12.292,-13))
    arc((-17.292,-18),(-22.292,-13));line((-22.292,-2.5))
    outline=Wire(edges)
    if d.edge_clearance:
        outline=outline.offset_2d(-d.edge_clearance,kind=Kind.ARC)
    blank=extrude(outline,5.155-d.thickness_clearance)
    # The spring thickens toward its fork; retain the thin contact finger.
    c=d.thickness_clearance
    roof=Face(Wire.make_polygon([(-30,-25,0),(30,-25,0),(30,-25,5.155-c),
                                 (12.5,-25,5.155-c),(9.5,-25,4.38-c),(-3,-25,4.38-c),
                                 (-14.7,-25,1.605-c),(-30,-25,1.605-c)],close=True))
    return one(blank.intersect(Solid.extrude(roof,(0,50,0))))


def build_accessory(output,spec):
    from dataclasses import asdict
    import hashlib,json
    from ._build import run_build
    from .project import PROJECT_ROOT
    from .exports import export_part_set
    if spec.accessory=='key':
        from .key_build import build_key
        return build_key(output)
    from .latch import build_latch, LatchDimensions
    constructors={'latch':build_latch, 'spring':build_spring,'runner_stop':build_runner_stop,
                  'facade_cap':build_facade_cap,'key_cap':build_key_cap}
    config={'part':spec.slug}
    if spec.accessory=='spring': config['spring_dimensions']=asdict(SpringDimensions())
    if spec.accessory=='latch': config['latch_dimensions']=asdict(LatchDimensions())
    notes={'latch':'Print flat. Latch outline relieved 0.10 mm and thickness reduced 0.15 mm for an easier fit. Test insertion and retention before use.',
           'spring':'Print flat. Nominal spring dimensions; no added fit relief.',
           'runner_stop':'Print flange down. Print two per populated runner tier.',
           'facade_cap':'Print closed face down. Repeat for each facade screw counterbore.',
           'key_cap':'Print closed face down with the socket upward. Fit over the key handle.'}
    def generate(state):
        return export_part_set(state.stage,spec,{spec.slug+'_single':constructors[spec.accessory]()},
                               kind=spec.accessory,print_note=notes[spec.accessory])
    digest=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    return run_build(PROJECT_ROOT,digest,generate,parameters=config,output=output,aliases=[f'latest/{spec.slug}'])
