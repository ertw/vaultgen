"""Indexed, blind, 120-degree printed helical cam joint for the S4 drawer.

The single interrupted helical thread enters one axial keyway. Its closed end
sets the locked position. The plain head sits in a recessed box seat. These
are prototype PLA fit dimensions, not an ISO thread or a measured printer fit.
Angles are right-handed around +Y (clockwise looking from inside the drawer).
"""
from dataclasses import dataclass
from math import cos, radians, sin
from build123d import Axis, Edge, Face, Plane, Solid, Wire
from .box import build_box, block
from .facade import build_facade


@dataclass(frozen=True)
class PrintedSpec:
    kind: str
    family: str = 'S'
    depth_units: int = 4
    height_units: int = 1

    @property
    def slug(self):
        return {'box': 's4_box_1f_printed_screw',
                'facade': 's1f_facade_printed_screw',
                'screw': 's4_facade_screw'}[self.kind]

    @property
    def name(self):
        return {'box': 'S4 Box 1F — Printed Screw',
                'facade': 'S1F Facade — Printed Screw',
                'screw': 'S4 Facade Indexed Screw'}[self.kind]


BOX_SPEC = PrintedSpec('box')
FACADE_SPEC = PrintedSpec('facade')
SCREW_SPEC = PrintedSpec('screw')


@dataclass(frozen=True)
class JointDimensions:
    radial_clearance: float = .30
    axial_clearance: float = .20
    shaft_radius: float = 4.0
    lug_radius: float = 5.4
    lug_crest_width: float = .8
    lug_span: float = 30.0
    turn: float = 120.0
    lead: float = 3.6
    lug_y: float = 5.8
    shaft_length: float = 8.1
    box_seat: float = 181.5
    facade_seat: float = 188.1
    axis_z: float = 23.5
    axis_x: float = 51.45
    head_gap: float = .20
    head_radius: float = 7.0
    head_thickness: float = 3.0
    head_chamfer: float = .5
    pilot_radius: float = 7.5
    pilot_length: float = 1.0
    boss_radius: float = 8.8
    blind_depth: float = 6.0
    head_seat: float = 185.2
    entry_phase: float = 75.0

    def __post_init__(self):
        # Only clearance tuning is currently supported; geometry relies on
        # the declared phase, envelopes and shoulder thicknesses.
        from math import isfinite
        for field in self.__dataclass_fields__:
            if not isfinite(getattr(self, field)):
                raise ValueError('Joint dimensions must be finite')
        if not .2 <= self.radial_clearance <= .4:
            raise ValueError('Radial clearance must be between 0.2 and 0.4 mm')
        if not .15 <= self.axial_clearance <= .3:
            raise ValueError('Axial clearance must be between 0.15 and 0.3 mm')
        for name, field in self.__dataclass_fields__.items():
            if name not in {'radial_clearance', 'axial_clearance'} and getattr(self, name) != field.default:
                raise ValueError(f'{name} is fixed for the indexed S4 joint')

    @property
    def travel(self): return self.lead * self.turn / 360

    @property
    def locked_head_y(self): return self.head_seat - self.head_gap

    @property
    def entry_head_y(self): return self.locked_head_y - self.travel


D = JointDimensions()


def _point(r, theta, y=0):
    a = radians(theta)
    return (r*cos(a), y, -r*sin(a))


def _cylinder(r, y, length):
    return Solid.make_cylinder(r, length, Plane(origin=(0,y,0), z_dir=(0,1,0)))


def _sector(r0, r1, start, end, y, length):
    """Annular sector with exact circular edges, extruded along the screw axis."""
    a, b, c, e = (_point(r0,start,y), _point(r1,start,y),
                  _point(r1,end,y), _point(r0,end,y))
    edges = [Edge.make_line(a,b),
             Edge.make_three_point_arc(b,_point(r1,(start+end)/2,y),c),
             Edge.make_line(c,e),
             Edge.make_three_point_arc(e,_point(r0,(start+end)/2,y),a)]
    return Solid.extrude(Face(Wire(edges)), (0,length,0))


def _thread(start, end, center_y, d=D, clearance=False):
    """Short trapezoidal helix. 45-degree flanks and a broad printable crest.

    The female track has axial and radial clearance independently; its angular
    end is deliberately closed at the nominal stop, without an extra branch.
    Analytic station wires are lofted into native smooth helical faces.
    """
    rc = d.radial_clearance if clearance else 0
    ac = d.axial_clearance if clearance else 0
    root = d.shaft_radius - .15
    outer = d.lug_radius + rc
    half = d.lug_crest_width / 2
    base = half + d.lug_radius - root
    # Expanding the trapezoid axially by rc preserves clearance on both flanks.
    extra = ac + rc if clearance else 0
    profile = [(root, -base-extra), (outer, -half-ac),
               (outer, half+ac), (root, base+extra)]
    count = max(3, round((end-start)/5))
    wires = []
    for i in range(count+1):
        angle = start + (end-start)*i/count
        y = center_y + d.lead*angle/360
        wires.append(Wire.make_polygon([_point(r,angle+d.entry_phase,y+v) for r,v in profile], close=True))
    return Solid.make_loft(wires)


def _checked(part, label):
    part.label = label
    if not part.is_valid or len(part.solids()) != 1 or len(part.shells()) != 1:
        raise ValueError(f'{label}: expected one valid solid and boundary shell')
    return part


def _draft_mask(y, length, clearance=0):
    # In the bottom view the lug narrows outward: 2.2 mm at R3.8,
    # 1.6 mm at R5.4. Its sides draft inward toward the shank on entry.
    points=[(-1.1-clearance,y,-3.8),(1.1+clearance,y,-3.8),
            (.8+clearance,y,-5.4-clearance),(-.8-clearance,y,-5.4-clearance)]
    return Solid.extrude(Face(Wire.make_polygon(points,close=True)),(0,length,0))


def _end_halfplane(d=D):
    # Same drafted trailing face as the male lug, at the end of its turn.
    points=[(-1.8125-.1875*z,-4,z) for z in (-20,20)]
    points += [(25,-4,20),(25,-4,-20)]
    return Solid.extrude(Face(Wire.make_polygon(points,close=True)),(0,20,0)).rotate(Axis.Y,d.turn)


def build_printed_screw(d=D):
    # Relieve the mating-side outer rim (Y=0) with a 45-degree chamfer.
    head = _cylinder(d.head_radius,-d.head_thickness,
                     d.head_thickness-d.head_chamfer).fuse(
        Solid.make_cone(d.head_radius,d.head_radius-d.head_chamfer,
                        d.head_chamfer,
                        Plane(origin=(0,-d.head_chamfer,0),z_dir=(0,1,0))))
    shank = _cylinder(d.shaft_radius,-.1,d.shaft_length-.3)
    tip = Solid.make_cone(d.shaft_radius,d.shaft_radius-.4,.4,
                         Plane(origin=(0,d.shaft_length-.4,0),z_dir=(0,1,0)))
    lug = _thread(0,d.lug_span,d.lug_y,d).intersect(_draft_mask(0,12))[0]
    part = head.fuse(shank,tip,lug)
    # Draft the 2 mm coin opening to the 1.4 mm driver over the 1.2 mm
    # scoop depth, preserving the curved floor and deep screwdriver slot.
    coin_radius = (6**2 + 1.2**2) / (2*1.2)
    coin_slot = Solid.make_cylinder(
        coin_radius,2,Plane(origin=(0,-1.8-coin_radius,-1),z_dir=(0,0,1)))
    coin_draft = Solid.extrude(Face(Wire.make_polygon([
        (-16,-3.1,-1.025), (-16,-3.1,1.025),
        (-16,-1.8,.7), (-16,-1.8,-.7)], close=True)), (32,0,0))
    coin_slot = coin_slot.intersect(coin_draft)[0]
    driver_slot = block(-3,-3.01,-.7,3,1.2,.7)
    part = part.cut(coin_slot,driver_slot)
    return _checked(part,SCREW_SPEC.name)


def _socket_cutters(d=D):
    # Coordinates local to the facade. The pilot starts one pilot_length behind its rear.
    bore = _cylinder(d.shaft_radius+d.radial_clearance,-d.pilot_length-.1,
                     d.blind_depth+d.pilot_length+.1)
    # Match the screw's entry axial position and its positive helical advance.
    center = d.entry_head_y-d.facade_seat+d.lug_y
    groove = _thread(-3,d.turn+d.lug_span,center,d,clearance=True).intersect(_end_halfplane(d))[0]
    # A single keyway admitting the whole lug, with 3 degree entry allowance.
    key = _draft_mask(-d.pilot_length-.1,
                       center+d.lead*(d.lug_span+3)/360+1+d.pilot_length+.1,
                       d.radial_clearance)
    return bore, groove, key


def build_printed_facade(d=D):
    part = build_facade(screw_bosses=False)
    boss = _cylinder(d.boss_radius,0,5.8)
    pilot = _cylinder(d.pilot_radius,-d.pilot_length+.4,d.pilot_length-.39)
    nose = Solid.make_cone(d.pilot_radius-.4,d.pilot_radius,.4,
                          Plane(origin=(0,-d.pilot_length,0),z_dir=(0,1,0)))
    local = boss.fuse(pilot,nose)
    for x in (-d.axis_x,d.axis_x):
        offset = (x,0,d.axis_z)
        part = part.fuse(local.translate(offset))
        part = part.cut(*[c.translate(offset) for c in _socket_cutters(d)])
    return _checked(part,FACADE_SPEC.name)


def build_printed_box(d=D):
    part = build_box()
    for x in (-d.axis_x,d.axis_x):
        # Opposed blind seats leave 1.7 mm of original wall between them.
        head_pocket = _cylinder(d.head_radius+d.radial_clearance,
                                d.box_seat-.1,d.head_seat-d.box_seat+.1)
        through = _cylinder(d.shaft_radius+d.radial_clearance,d.box_seat-.1,
                            d.facade_seat-d.box_seat+.2)
        key = _draft_mask(d.box_seat-.1,d.facade_seat-d.box_seat+.2,
                          d.radial_clearance)
        pilot = _cylinder(d.pilot_radius+d.radial_clearance,
                          d.facade_seat-d.pilot_length-.2,d.pilot_length+.3)
        lead = Solid.make_cone(d.pilot_radius+d.radial_clearance,
                              d.pilot_radius+d.radial_clearance+.4,.4,
                              Plane(origin=(0,d.facade_seat-.4,0),z_dir=(0,1,0)))
        part = part.cut(*[c.translate((x,0,d.axis_z))
                          for c in (head_pocket,through,key,pilot,lead)])
    return _checked(part,BOX_SPEC.name)


def placed_screw(x=D.axis_x, angle=0, d=D):
    """Assembly pose on the helical path: 0 = inserted; 120 = locked."""
    y = d.entry_head_y + d.lead*angle/360
    return build_printed_screw(d).rotate(Axis.Y,angle).translate((x,y,d.axis_z))
