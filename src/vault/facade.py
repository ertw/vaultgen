"""Parametric facades using the measured S1F native feature definitions.

Rear seating plane Y=0, front Y=10. X/Z share the module datum. The source
STL is used only by research tools, never by this constructor.
"""
from dataclasses import dataclass
from build123d import Edge, Wire, Face, Solid, Plane
from .spec import DEFAULT_SPEC
from .drawer import DrawerLayout, drawer_spec
from .envelope import _smooth_sleeve, EnvelopeDimensions
from .shell import _rounded_rect
from .shadow_gap import DEFAULT_GAP, perimeter_rebate

@dataclass(frozen=True)
class FacadeSpec:
    family: str = 'S'
    height_units: int = 1
    def __post_init__(self):
        drawer_spec(self)
    @property
    def name(self): return f'{self.family}{self.height_units}F Facade'
    @property
    def slug(self): return f'{self.family.lower()}{self.height_units}f_facade'

SPEC = FacadeSpec()

def rectangle(x0,z0,x1,z1,r,y):
    return _rounded_rect(x0,z0,x1,z1,r,lambda x,z:(x,y,z))

def cylinder(radius,y,depth,x=0,z=23.5):
    return Solid.make_cylinder(radius,depth,Plane(origin=(x,y,z),z_dir=(0,1,0)))

def opening_wire(y):
    # Two R18.125 side arcs, R20.125 upper/lower lobes, short notch shoulders.
    z=23.694
    pts=[(14.10,11.375),(15.25,13.13),(-15.25,13.13),(-14.10,11.375),
         (-14.10,-11.375),(-15.25,-13.13),(15.25,-13.13),(14.10,-11.375)]
    p=lambda t:(t[0]-.01,y,z+t[1])
    es=[Edge.make_line(p(pts[0]),p(pts[1])),
        Edge.make_three_point_arc(p(pts[1]),p((0,20.125)),p(pts[2])),
        Edge.make_line(p(pts[2]),p(pts[3])),
        Edge.make_three_point_arc(p(pts[3]),p((-18.125,0)),p(pts[4])),
        Edge.make_line(p(pts[4]),p(pts[5])),
        Edge.make_three_point_arc(p(pts[5]),p((0,-20.125)),p(pts[6])),
        Edge.make_line(p(pts[6]),p(pts[7])),
        Edge.make_three_point_arc(p(pts[7]),p((18.125,0)),p(pts[0]))]
    return Wire(es)

def build_facade(gap=DEFAULT_GAP, *, spec=DEFAULT_SPEC):
    layout = DrawerLayout(spec)
    spec = layout.spec
    pocket_width = 62.13 + layout.width_delta
    base=_smooth_sleeve(spec,EnvelopeDimensions())
    face=min(base.faces(),key=lambda f:f.center().Y)
    wire=face.outer_wire()
    wires=[]
    # Smooth convex roll measured at section stations; native B-spline loft.
    for y,inset in [(0,0),(1,.013),(2,.058),(3,.175),(4,.376),(5,.7),
                    (6,1.15),(7,1.765),(8,2.569),(9,3.6),(10,5)]:
        w=wire if inset==0 else wire.offset_2d(-inset)
        if Face(w).area>face.area: w=wire.offset_2d(inset)
        wires.append(w.translate((0,y,0)))
    part=Solid.make_loft(wires)
    pocket=Solid.extrude(rectangle(-pocket_width,5,pocket_width,spec.height-5,3,-.01),(0,2.41,0))
    # The upper/lower pocket bulges clear the finger-opening reinforcement.
    for top in [False,True]:
        profile=[(-14.45,5),(-10.53,4.586),(-2.439,3.046),(0,2.861),(2.439,3.046),(10.53,4.586),(14.45,5)]
        points=[(x,-.01,spec.height-z if top else z) for x,z in profile]
        edge=Edge.make_spline(points)
        cap=Face(Wire([edge,Edge.make_line(points[-1],points[0])]))
        pocket=pocket.fuse(Solid.extrude(cap,(0,2.41,0)))
    part=part.cut(pocket)
    # Side pockets run to Y=5.75; their inner walls slope around the handle.
    for side in [-1,1]:
        pocket=Solid.extrude(rectangle(-pocket_width,5,pocket_width,spec.height-5,3,2.399),(0,3.351,0))
        a,b=22.36,38.23
        pts=[(side*a,2.399,-1),(side*(spec.half_width+10),2.399,-1),(side*(spec.half_width+10),5.75,-1),(side*b,5.75,-1)]
        wedge=Solid.extrude(Face(Wire.make_polygon(pts,close=True)),(0,0,spec.height+2))
        part=part.cut(*pocket.intersect(wedge))
    # Flat-sided bosses share exact axes with the tray. S repeats its pair;
    # M/L retain the lock pair and add outer screws at every runner tier.
    for x,z in layout.screw_positions:
        side = 1 if x > 0 else -1
        boss=cylinder(6.8,.5,5.25,x,z)
        clip_start = x-3.78 if side > 0 else x-16.22
        clip=Solid.make_box(20,6,20,Plane(origin=(clip_start,0,z-10)))
        boss=boss.intersect(clip)[0]
        foot=Solid.make_cone(6.3,6.8,.5,Plane(origin=(x,0,z),z_dir=(0,1,0))).intersect(clip)[0]
        part=part.fuse(boss,foot)
        part=part.cut(cylinder(2.2,-.01,6,x,z),cylinder(5,5.9,4.2,x,z),
                      Solid.make_cone(4.85,5,.15,Plane(origin=(x,5.75,z),z_dir=(0,1,0))))
    part=part.cut(Solid.extrude(Face(opening_wire(2.399)),(0,3.802,0)))
    rings=[Wire.make_circle(r,Plane(origin=(0,y,23.489),z_dir=(0,1,0)))
           for y,r in [(6.199,17.6),(7,17.15),(8,17.6),(9,17.15),(10.01,17.6)]]
    part=part.cut(Solid.make_loft(rings))
    # Shallow front-side label/lever recess, opening onto the right perimeter.
    recess=Solid.extrude(rectangle(32,13.5,spec.half_width+17.6,33.5,9.99,7.91),(0,2.2,0))
    part=part.cut(recess)
    if gap is not None:part=perimeter_rebate(part,0,1,spec=spec,gap=gap)
    part.label=FacadeSpec(spec.family, spec.height_units).name
    if not part.is_valid or len(part.solids())!=1 or len(part.shells())!=1:
        raise ValueError('Facade must be one valid connected solid and boundary shell')
    return part
