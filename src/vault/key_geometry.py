"""Editable native geometry for the original Vault key exterior.

All dimensions are mm. The shaft is Z, its bottom face is Z=0, and the
handle/oval wing lie along X. This module contains only curves and dimensions;
loading the purchased mesh belongs to measurement tools. Small embossed marks
are omitted. The capsule foot blend uses an analytic cubic section and native revolutions.
"""

from dataclasses import dataclass
from math import cos, sin, pi, sqrt

from build123d import Axis, Edge, Face, Plane, Solid, Wire


@dataclass(frozen=True)
class KeyExteriorDimensions:
    tooth_count: int = 20
    gear_outer_radius: float = 14.08
    gear_root_radius: float = 11.2
    gear_height: float = 6.4
    gear_transition_height: float = 1.0
    gear_transition_spread: float = .8
    wing_length: float = 45.0
    wing_width: float = 21.757
    wing_thickness: float = 3.2
    wing_round: float = 1.0
    flange_bottom: float = 7.4
    flange_top: float = 10.8
    flange_bevel: float = .8
    neck_radius: float = 14.888
    neck_straight_top: float = 12.208
    shoulder_radius: float = 16.968
    shoulder_start: float = 14.508
    shoulder_top: float = 18.4
    shoulder_bevel: float = .5
    shoulder_bevel_bottom: float = 17.9
    rim_height: float = 16.5
    rim_round: float = .635
    rim_projection: float = .4
    handle_end_center: float = 9.3135
    handle_radius: float = 4.5415
    handle_foot_spread: float = 2.0
    handle_blend_height: float = 5.3
    handle_rim_bottom: float = 27.417
    handle_rim_round: float = .3
    handle_bevel_bottom: float = 31.917
    handle_top: float = 33.417
    handle_bevel: float = 1.5
    dimple_radius: float = 4.0
    dimple_depth: float = 1.05


D = KeyExteriorDimensions()
SOURCE_ORIGIN = (9001.65625, 1862.82269287, 6.90078592)


def _solid(shape):
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError("Key exterior must be connected")
        shape = shape[0]
    if not shape.is_valid or len(shape.solids()) != 1:
        raise ValueError("Invalid key exterior")
    return shape.solids()[0]


def _p(r, angle, z=0):
    return (r * cos(angle), r * sin(angle), z)


def _circle(radius, z=0):
    return Wire.make_circle(radius, Plane(origin=(0, 0, z)))


def _extrude(wire, height):
    return Solid.extrude(Face(wire), (0, 0, height))


def gear_outline(z=0):
    """Twenty repeated native tooth profiles: root/tip arcs and 20° flanks.

    The original has flat tooth tips and rounded roots. The dimensions here
    describe one tooth's construction features, not a sampled mesh contour.
    """
    edges = []
    root = _p(D.gear_root_radius, pi / D.tooth_count)
    root_mid = _p(11.35356, 6.54 * pi / 180)
    root_end = (11.9287, .96185, 0)
    shoulder_start = (12.5547, .958435, 0)
    shoulder_mid = (12.6392, .9511, 0)
    shoulder_end = (12.7207, .92926, 0)
    flank_end = (13.91016, .496277, 0)
    tip_mid = (14.0213, .4028, 0)
    tip_end = (14.07617, .263855, 0)

    def point(p, angle, mirror=False):
        x, y = p[:2]
        if mirror:
            y = -y
        return (x*cos(angle)-y*sin(angle), x*sin(angle)+y*cos(angle), z)

    for index in range(D.tooth_count):
        angle = index * 2*pi / D.tooth_count
        def q(p, mirror=False):
            return point(p, angle, mirror)
        edges.extend([
            Edge.make_three_point_arc(q(root, True), q(root_mid, True), q(root_end, True)),
            Edge.make_line(q(root_end, True), q(shoulder_start, True)),
            Edge.make_three_point_arc(q(shoulder_start, True), q(shoulder_mid, True), q(shoulder_end, True)),
            Edge.make_line(q(shoulder_end, True), q(flank_end, True)),
            Edge.make_three_point_arc(q(flank_end, True), q(tip_mid, True), q(tip_end, True)),
            Edge.make_line(q(tip_end, True), q(tip_end)),
            Edge.make_three_point_arc(q(tip_end), q(tip_mid), q(flank_end)),
            Edge.make_line(q(flank_end), q(shoulder_end)),
            Edge.make_three_point_arc(q(shoulder_end), q(shoulder_mid), q(shoulder_start)),
            Edge.make_line(q(shoulder_start), q(root_end)),
            Edge.make_three_point_arc(q(root_end), q(root_mid), q(root)),
        ])
    return Wire(edges)


def _flange_outline(z=0, inset=0):
    """Rounded-square collar with four scallops, each quadrant using arcs."""
    points = [(16.092, 0), (16.315, 1.025), (16.95, 1.87),
              (17.94, 3.15), (18.25, 4.44), (17.85, 7.1),
              (17.214, 9.813), (14.551, 14.551), (9.813, 17.214),
              (7.1, 17.85), (4.44, 18.25), (3.15, 17.94),
              (1.87, 16.95), (1.025, 16.315), (0, 16.092)]
    edges = []
    for quadrant in range(4):
        angle = quadrant*pi/2
        def p(i):
            x, y = points[i]
            return (x*cos(angle)-y*sin(angle), x*sin(angle)+y*cos(angle), z)
        for i in range(0, len(points)-2, 2):
            edges.append(Edge.make_three_point_arc(p(i), p(i+1), p(i+2)))
    wire = Wire(edges)
    return wire.offset_2d(-inset) if inset else wire


def capsule_outline(radius, z=0):
    a = D.handle_end_center
    return Wire([
        Edge.make_line((-a, -radius, z), (a, -radius, z)),
        Edge.make_three_point_arc((a, -radius, z), (a+radius, 0, z), (a, radius, z)),
        Edge.make_line((a, radius, z), (-a, radius, z)),
        Edge.make_three_point_arc((-a, radius, z), (-a-radius, 0, z), (-a, -radius, z)),
    ])


def build_gear_blank():
    """The lower gear/oval wing, ending at the intended Z=7.4 join plane."""
    wire = gear_outline()
    gear = _extrude(wire, D.gear_height)
    # Native planar offset preserves tooth-root shape through the upper bevel.
    # Positive offsets share the same topology; the tiny initial offset
    # avoids the twisted correspondence produced by mixing 220 and 300 edges.
    transition = Solid.make_loft([
        wire.offset_2d(.0001).translate((0, 0, D.gear_height)),
        wire.offset_2d(D.gear_transition_spread).translate((0, 0, D.flange_bottom)),
    ], ruled=True)
    wing = _wing()
    return _solid(gear.fuse(transition, wing, wing.rotate(Axis.Z, 180)))


def _wing():
    """One oval lobe with a variable native edge round and two throat blends."""
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.collections import Array1_gp_Pnt2d
    from OCP.gp import gp_Pnt2d

    ellipse = Wire([Edge.make_ellipse(D.wing_length/2, D.wing_width/2)])
    blank = _extrude(ellipse, D.wing_thickness)
    rounding = BRepFilletAPI_MakeFillet(blank.wrapped)
    for edge in blank.edges():
        if edge.length < D.wing_thickness*2:
            continue
        law = Array1_gp_Pnt2d(1, 17)
        for i in range(17):
            fraction = i/16
            x = edge.position_at(fraction).X / (D.wing_length/2)
            law.SetValue(i+1, gp_Pnt2d(fraction, D.wing_round*max(.15, 1-2*(1-abs(x))**1.5)))
        rounding.Add(law, edge.wrapped)
    rounding.Build()
    if not rounding.IsDone():
        raise ValueError("Unable to construct the oval wing's variable round")
    blank = Solid(rounding.Shape())
    # Keep only the lobe: the purchased wing leaves the central tooth valleys
    # open instead of filling the entire ellipse across the pinion.
    wedge = _extrude(Wire.make_polygon([(0, 0, -.1), (30, -38.4, -.1),
                                        (30, 38.4, -.1)], close=True), D.wing_thickness+.2)
    wing = _solid(blank.intersect(wedge))

    def notch(z):
        h = max(0, min(z, D.wing_thickness-z))
        delta = .2*(1-sqrt(max(0, 1-(1-min(h, 1))**2)))
        def p(x, y):
            return (x, y, z)
        a = p(8.5059, 10.0722)
        b = p(9.459, 8.9499-delta)
        c = p(12.291, 9.1126-2*delta)
        edges = [
            Edge.make_line(p(7, 20), p(8.577, 10.9626)),
            Edge.make_line(p(8.577, 10.9626), a),
            Edge.make_bezier(a, p(8.38, 9.05-delta), p(8.97, 8.95-delta), b),
            Edge.make_bezier(b, p(10.4, 8.92-delta), p(11.3, 9.46-1.5*delta), c),
            Edge.make_line(c, p(14, 8.7-2*delta)),
            Edge.make_line(p(14, 8.7-2*delta), p(14, 20)),
            Edge.make_line(p(14, 20), p(7, 20)),
        ]
        return Wire(edges)

    cut = Solid.make_loft([notch(z) for z in (-.1, 0, .25, 1, 2.2, 2.95, 3.2, 3.3)], ruled=True)
    wing = _solid(wing.cut(cut, cut.mirror(Plane.XZ)))
    return wing


def build_handle_blank():
    """Upper collar/handle, with its original assembly coordinates retained."""
    bottom = _flange_outline(D.flange_bottom, D.flange_bevel)
    outline = _flange_outline(D.flange_bottom+D.flange_bevel)
    collar = Solid.make_loft([bottom, outline], ruled=True).fuse(
        _extrude(outline, D.flange_top-D.flange_bottom-D.flange_bevel))
    neck = Solid.make_cylinder(D.neck_radius, D.neck_straight_top-D.flange_top,
                               Plane(origin=(0, 0, D.flange_top)))
    shoulder = Solid.make_loft([
        _circle(D.neck_radius, D.neck_straight_top),
        _circle(D.shoulder_radius, D.shoulder_start),
    ], ruled=True).fuse(Solid.make_cylinder(
        D.shoulder_radius, D.shoulder_bevel_bottom-D.shoulder_start,
        Plane(origin=(0, 0, D.shoulder_start))))
    bevel = Solid.make_loft([
        _circle(D.shoulder_radius, D.shoulder_bevel_bottom),
        _circle(D.shoulder_radius-D.shoulder_bevel, D.shoulder_top),
    ], ruled=True)
    rim = Solid.make_torus(D.shoulder_radius+D.rim_projection-D.rim_round, D.rim_round,
                           Plane(origin=(0, 0, D.rim_height)))
    # Opposed short keys on the collar preserve the purchased indexing tabs.
    tab = Solid.make_box(6.3975, 3.3256, 3.704, Plane(origin=(13.5, -1.6628, D.flange_top)))
    vertical = [edge for edge in tab.edges() if abs(edge.tangent_at(0).Z) > .99]
    tab = tab.fillet(.8, vertical)
    tab1 = tab.rotate(Axis.Z, 45).translate((-.0543, .0543, 0))
    tab2 = tab.rotate(Axis.Z, 225).translate((-.0543, .0543, 0))
    body = collar.fuse(neck, shoulder, bevel, rim, tab1, tab2)
    # One cubic profile forms the long smooth capsule foot. Native revolutions
    # form both ends; the matching side section is extruded along the handle.
    # This construction is monotone and avoids interpolation loft ripples.
    r, z = D.handle_radius, D.shoulder_top
    a = D.handle_end_center
    h = D.handle_blend_height
    def curve(x=0, sign=1):
        return Edge.make_bezier((x, sign*(r+D.handle_foot_spread), z),
                                (x, sign*(r+.25), z),
                                (x, sign*r, z+2), (x, sign*r, z+h))
    section = Wire([curve(-a),
                    Edge.make_line((-a, r, z+h), (-a, -r, z+h)),
                    curve(-a, -1).reversed(),
                    Edge.make_line((-a, -r-D.handle_foot_spread, z),
                                   (-a, r+D.handle_foot_spread, z))])
    middle = Solid.extrude(Face(section), (2*a, 0, 0))
    half = Wire([curve(), Edge.make_line((0, r, z+h), (0, 0, z+h)),
                 Edge.make_line((0, 0, z+h), (0, 0, z)),
                 Edge.make_line((0, 0, z), (0, r+D.handle_foot_spread, z))])
    end = Solid.revolve(Face(half), 360, Axis.Z)
    foot = middle.fuse(end.translate((-a, 0, 0)), end.translate((a, 0, 0)))
    handle = _extrude(capsule_outline(D.handle_radius, D.shoulder_top+D.handle_blend_height),
                      D.handle_bevel_bottom-D.shoulder_top-D.handle_blend_height)
    top = Solid.make_loft([capsule_outline(D.handle_radius, D.handle_bevel_bottom),
                          capsule_outline(D.handle_radius-D.handle_bevel, D.handle_top)], ruled=True)
    # The subtle capsule rim has a circular vertical section.
    lip_wires = [capsule_outline(D.handle_radius + D.handle_rim_round*sin(t),
                                D.handle_rim_bottom+D.handle_rim_round*(1-cos(t)))
                 for t in (0, pi/4, pi/2, 3*pi/4, pi)]
    lip = Solid.make_loft(lip_wires)
    body = _solid(body.fuse(foot, handle, top, lip))
    bowl = Solid.make_sphere(D.dimple_radius, Plane(origin=(
        -9.3008, 0, D.handle_top+D.dimple_radius-D.dimple_depth)))
    return _solid(body.cut(bowl))


def build_key_blank():
    """Complete single-piece key with its integrated drive pinion."""
    return _solid(build_gear_blank().fuse(build_handle_blank()))
