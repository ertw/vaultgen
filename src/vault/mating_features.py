"""Reusable native mating shapes, defined in millimetres at their skin datum.

The builders use planes, circular arcs and a handful of cubic corner blends.
Placement belongs to the module layout; none of these functions reads an STL
or a measured contour table. Lower features point below Z=0, upper features
above it. A 0.02 mm hidden root band makes attachment a volume union.
"""

from dataclasses import dataclass, fields
from math import atan2, cos, hypot, isfinite, pi, radians, sin, sqrt, tan

from build123d import Axis, Edge, Face, Plane, Solid, Wire


ROOT_OVERLAP = 0.02


class _PositiveDimensions:
    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field.name} must be a finite positive dimension")


def _line(a, b):
    return Edge.make_line(a, b)


def _arc(a, middle, b):
    return Edge.make_three_point_arc(a, middle, b)


def _one(shape):
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError("A mating feature must be connected")
        shape = shape[0]
    if not shape.is_valid or len(shape.solids()) != 1:
        raise ValueError("Invalid native mating feature")
    return shape.solids()[0]


def _prism(points, direction):
    return Solid.extrude(Face(Wire.make_polygon(points)), direction)


def _circle_mid(center, start, end, positive=True):
    a = atan2(start[1] - center[1], start[0] - center[0])
    b = atan2(end[1] - center[1], end[0] - center[0])
    if positive and b < a:
        b += 2 * pi
    if not positive and b > a:
        b -= 2 * pi
    radius = hypot(start[0] - center[0], start[1] - center[1])
    return (
        center[0] + radius * cos((a + b) / 2),
        center[1] + radius * sin((a + b) / 2),
    )


def _circle_join(c1, r1, c2, r2):
    distance = hypot(c2[0] - c1[0], c2[1] - c1[1])
    vector = ((c2[0] - c1[0]) / distance, (c2[1] - c1[1]) / distance)
    return (
        tuple(c1[i] + r1 * vector[i] for i in range(2)),
        tuple(c2[i] - r2 * vector[i] for i in range(2)),
    )


@dataclass(frozen=True)
class LowerClosedDovetailDimensions(_PositiveDimensions):
    """Closed-end 45-degree dovetail; origin at its outer wall and closed end."""

    height: float = 4.9697
    root_width: float = 12.3486
    shoulder_height: float = 0.2633
    outer_radius: float = 1.0
    flank_radius: float = 0.5
    tip_radius: float = 2.0
    tip_center_y: float = 44.27
    notch_x: float = 6.9186
    notch_y: float = 12.73
    notch_slope: float = 1.27624


def lower_closed_end_dovetail(d=LowerClosedDovetailDimensions()):
    """Left-handed dovetail, with X=0 on its outer vertical wall."""
    c = sqrt(0.5)
    bottom = -d.height
    upper = (d.root_width + d.flank_radius, -d.shoulder_height)
    lower_z = bottom + d.flank_radius
    lower = (upper[0] + upper[1] - lower_z - 2 * sqrt(2) * d.flank_radius, lower_z)
    outer = (d.outer_radius, bottom + d.outer_radius)
    r = d.flank_radius

    def p(x, z):
        return (x, 0, z)

    a, b, e = p(0, ROOT_OVERLAP), p(0, outer[1]), p(outer[0], bottom)
    f = p(lower[0], bottom)
    g = p(lower[0] + r * c, lower[1] + r * c)
    h = p(upper[0] - r * c, upper[1] - r * c)
    i, j = p(d.root_width, upper[1]), p(d.root_width, ROOT_OVERLAP)
    cross = Face(
        Wire(
            [
                _line(a, b),
                _arc(
                    b,
                    p(outer[0] - d.outer_radius * c, outer[1] - d.outer_radius * c),
                    e,
                ),
                _line(e, f),
                _arc(f, p(lower[0] + r, lower[1]), g),
                _line(g, h),
                _arc(h, p(upper[0] - r * cos(pi / 8), upper[1] - r * sin(pi / 8)), i),
                _line(i, j),
                _line(j, a),
            ]
        )
    )
    body = Solid.extrude(cross, (0, d.tip_center_y + d.tip_radius + 1, 0))
    # Two diagonal mating steps meet the circular outer tip in plan.
    max_x = d.root_width + d.height
    tip_x, tip_y, radius = d.tip_radius, d.tip_center_y, d.tip_radius
    diagonal = tip_x + tip_y + radius * sqrt(2)
    points = [
        (0, 0),
        (max_x, 0),
        (max_x, d.notch_y - d.notch_slope * (max_x - d.notch_x)),
        (d.notch_x, d.notch_y),
        (max_x, d.notch_y),
        (max_x, diagonal - max_x),
        (tip_x + radius * c, tip_y + radius * c),
    ]

    def q(point):
        return (*point, bottom - 1)

    edges = [_line(q(a), q(b)) for a, b in zip(points, points[1:])]
    edges += [
        _arc(q(points[-1]), q((tip_x, tip_y + radius)), q((0, tip_y))),
        _line(q((0, tip_y)), q(points[0])),
    ]
    envelope = Solid.extrude(Face(Wire(edges)), (0, 0, d.height + 2))
    return _one(body.intersect(envelope))


@dataclass(frozen=True)
class UpperOpenDovetailDimensions(_PositiveDimensions):
    """Upper tapered dovetail, centered in X with its open-end face at Y=0."""

    root_half_width: float = 10.0
    height: float = 4.8
    flank_angle: float = 50.0
    plan_angle: float = 7.75
    crown_radius: float = 0.6
    entry_length: float = 35.2476
    root_ramp_radius: float = 9.607
    crown_ramp_radius: float = 6.71835
    rear_corner_width: float = 14.15
    rear_corner_depth: float = 4.1


def upper_open_end_dovetail(d=UpperOpenDovetailDimensions()):
    angle = radians(d.flank_angle)
    slope, cs, sn = tan(angle), cos(angle), sin(angle)
    cz = d.height - d.crown_radius
    cx = d.root_half_width + slope * cz - d.crown_radius / cs
    r = d.crown_radius

    def p(x, z):
        return (x, 0, z)

    a, b = p(-d.root_half_width, -ROOT_OVERLAP), p(-d.root_half_width, 0)
    c, e = p(-cx - r * cs, cz - r * sn), p(-cx, d.height)
    f, g = p(cx, d.height), p(cx + r * cs, cz - r * sn)
    h, i = p(d.root_half_width, 0), p(d.root_half_width, -ROOT_OVERLAP)
    # Three chords replace each small crown round. Sweeping planar facets
    # avoids the dense, irregular triangulation of the oblique cylinders.
    # Keep the tangent endpoints and crown height; nominal chord error < .05 mm.
    crown_points = [
        p(-cx + r * cos(pi + angle - (pi / 2 + angle) * step / 3),
          cz + r * sin(pi + angle - (pi / 2 + angle) * step / 3))
        for step in range(4)
    ]
    left_crown = [_line(a, b) for a, b in zip(crown_points, crown_points[1:])]
    right_points = [(-point[0], point[1], point[2]) for point in reversed(crown_points)]
    right_crown = [_line(a, b) for a, b in zip(right_points, right_points[1:])]
    section = Face(
        Wire(
            [
                _line(a, b),
                _line(b, c),
                *left_crown,
                _line(e, f),
                *right_crown,
                _line(g, h),
                _line(h, i),
                _line(i, a),
            ]
        )
    )
    length = d.entry_length + 5
    taper = tan(radians(d.plan_angle))
    body = _one(
        Solid.extrude(section, (length * taper, -length, 0)).intersect(
            Solid.extrude(section, (-length * taper, -length, 0))
        )
    )
    # A single cubic on each rear corner preserves the slightly squared curve.
    w, depth = d.rear_corner_width, d.rear_corner_depth

    def q(x, y):
        return (x, y, -ROOT_OVERLAP - 1)

    points = [
        q(-w, -length),
        q(w, -length),
        q(w, -depth),
        q(d.root_half_width, 0),
        q(-d.root_half_width, 0),
        q(-w, -depth),
    ]
    handle_y = depth * (0.7 / 4.1)
    # Nominal controls: (14.15,-.7) and (13.4,0).
    handle_x = d.root_half_width + (w - d.root_half_width) * (3.4 / 4.15)
    edges = [
        _line(points[0], points[1]),
        _line(points[1], points[2]),
        Edge.make_bezier(points[2], q(w, -handle_y), q(handle_x, 0), points[3]),
        _line(points[3], points[4]),
        Edge.make_bezier(points[4], q(-handle_x, 0), q(-w, -handle_y), points[5]),
        _line(points[5], points[0]),
    ]
    body = _one(body.intersect(Solid.extrude(Face(Wire(edges)), (0, 0, d.height + 2))))
    c1 = (-d.entry_length, 9.5763)
    c2 = (-d.entry_length + 11.6357, d.height - 6.7155)
    r1, r2 = d.root_ramp_radius, d.crown_ramp_radius
    j1, j2 = _circle_join(c1, r1, c2, r2)
    lo, hi = -ROOT_OVERLAP, d.height
    start = (c1[0] + sqrt(r1 * r1 - (lo - c1[1]) ** 2), lo)
    end = (c2[0] - sqrt(r2 * r2 - (hi - c2[1]) ** 2), hi)
    extent = w + 2

    def yz(point):
        return (-extent, *point)

    edges = [
        _arc(yz(start), yz(_circle_mid(c1, start, j1)), yz(j1)),
        _line(yz(j1), yz(j2)),
        _arc(yz(j2), yz(_circle_mid(c2, j2, end, False)), yz(end)),
        _line(yz(end), yz((1, hi))),
        _line(yz((1, hi)), yz((1, lo))),
        _line(yz((1, lo)), yz(start)),
    ]
    return _one(body.intersect(Solid.extrude(Face(Wire(edges)), (2 * extent, 0, 0))))


def _lower_entry(x, width, bottom, rear, crown, crown_radius, root, root_radius):
    """Two tangent-like circular entry ramps, with a short constant root band."""
    j1, j2 = _circle_join(crown, crown_radius, root, root_radius)
    low = (crown[0] - sqrt(max(0, crown_radius**2 - (bottom - crown[1]) ** 2)), bottom)
    high = (root[0] + sqrt(root_radius**2 - (-0.001 - root[1]) ** 2), -0.001)

    def p(point):
        return (x, *point)

    edges = [
        _arc(p(low), p(_circle_mid(crown, low, j1, False)), p(j1)),
        _line(p(j1), p(j2)),
        _arc(p(j2), p(_circle_mid(root, j2, high)), p(high)),
        _line(p(high), p((high[0], ROOT_OVERLAP))),
        _line(p((high[0], ROOT_OVERLAP)), p((rear, ROOT_OVERLAP))),
        _line(p((rear, ROOT_OVERLAP)), p((rear, bottom))),
        _line(p((rear, bottom)), p(low)),
    ]
    return Solid.extrude(Face(Wire(edges)), (width, 0, 0))


@dataclass(frozen=True)
class LowerOpenDovetailDimensions(_PositiveDimensions):
    """Lower carrier and detent, outer wall X=0 and open-end face Y=0."""

    height: float = 4.5
    root_width: float = 18.5232
    flank_angle: float = 50.0
    plan_angle: float = 7.75
    entry_length: float = 31.626
    outer_radius: float = 1.2
    rear_radius: float = 5.0
    rear_crown_radius: float = 1.1
    central_symmetry_x: float = 11.6016
    tongue_center_x: float = 12.1202
    tongue_width: float = 6.9004
    tongue_projection: float = 0.7063
    tongue_bevel: float = 0.4
    tongue_rear_radius: float = 1.5


def _lower_carrier(d):
    bottom = -d.height
    sweep = d.entry_length + 8.374
    front = -sweep - 6
    slope, taper = tan(radians(d.flank_angle)), tan(radians(d.plan_angle))
    c, r = sqrt(0.5), d.outer_radius

    def p(x, z):
        return (x, 0, z)

    profile = Face(
        Wire.make_polygon(
            [
                p(-25, ROOT_OVERLAP),
                p(-25, bottom),
                p(d.root_width - slope * bottom, bottom),
                p(d.root_width, 0),
                p(d.root_width, ROOT_OVERLAP),
            ]
        )
    )
    body = Solid.extrude(profile, (sweep * taper, -sweep, 0))
    outside = Face(
        Wire(
            [
                _line(p(0, ROOT_OVERLAP), p(0, bottom + r)),
                _arc(p(0, bottom + r), p(r - r * c, bottom + r - r * c), p(r, bottom)),
                _line(p(r, bottom), p(40, bottom)),
                _line(p(40, bottom), p(40, ROOT_OVERLAP)),
                _line(p(40, ROOT_OVERLAP), p(0, ROOT_OVERLAP)),
            ]
        )
    )
    body = _one(body.intersect(Solid.extrude(outside, (0, -sweep, 0))))
    # The outer rounded rear corner is trimmed 0.2 mm before its tangent.
    radius = d.rear_radius
    corner = (radius, 0.2 - radius)
    right_start = d.root_width + 5.5484

    def q(x, y):
        return (x, y, bottom - 1)

    far_x = right_start + (-5 - front) * (5.57 / 40.9742)
    points = [
        q(0, front),
        q(far_x, front),
        q(right_start, -5),
        q(d.root_width + 0.5484, 0),
        q(radius, 0.2),
        q(0, corner[1]),
    ]
    edges = [
        _line(points[0], points[1]),
        _line(points[1], points[2]),
        Edge.make_bezier(
            points[2],
            q(right_start - 0.65, -1.3742),
            q(d.root_width + 3.7984, 0),
            points[3],
        ),
        _line(points[3], points[4]),
        _arc(points[4], q(radius - radius * c, corner[1] + radius * c), points[5]),
        _line(points[5], points[0]),
    ]
    body = _one(body.intersect(Solid.extrude(Face(Wire(edges)), (0, 0, d.height + 2))))
    crown = (-d.entry_length + 11.5018, bottom + 6.95)
    root = (-d.entry_length, -9.8942)
    body = _one(
        body.intersect(_lower_entry(-8, 45, bottom, 0, crown, 6.95, root, 9.91543))
    )

    # A low cubic roll follows the rear crown; it is deliberately a single face.
    def yz(y, z):
        return (-8, y, z)

    rear = Face(
        Wire(
            [
                _line(yz(front, bottom), yz(-1, bottom)),
                Edge.make_bezier(
                    yz(-1, bottom),
                    yz(-0.62, bottom),
                    yz(0, bottom + 0.27),
                    yz(0, bottom + 0.7),
                ),
                _line(yz(0, bottom + 0.7), yz(0, ROOT_OVERLAP)),
                _line(yz(0, ROOT_OVERLAP), yz(front, ROOT_OVERLAP)),
                _line(yz(front, ROOT_OVERLAP), yz(front, bottom)),
            ]
        )
    )
    body = _one(body.intersect(Solid.extrude(rear, (45, 0, 0))))
    # Roll the crown around the outer plan corner with a surface of revolution.
    rr = d.rear_crown_radius

    def rz(rad, z):
        return (corner[0] + rad, corner[1], z)

    edges = [
        _line(rz(0, bottom), rz(radius - rr, bottom)),
        _arc(
            rz(radius - rr, bottom),
            rz(radius - rr + rr * c, bottom + rr - rr * c),
            rz(radius, bottom + rr),
        ),
        _line(rz(radius, bottom + rr), rz(radius, ROOT_OVERLAP)),
        _line(rz(radius, ROOT_OVERLAP), rz(0, ROOT_OVERLAP)),
        _line(rz(0, ROOT_OVERLAP), rz(0, bottom)),
    ]
    rolling = Solid.revolve(Face(Wire(edges)), 360, Axis((*corner, 0), (0, 0, 1)))
    allowed = rolling.fuse(
        Solid.make_box(50, -front + 2, 8).translate((corner[0], front, -6)),
        Solid.make_box(70, corner[1] - front, 8).translate((-25, front, -6)),
    )
    return _one(body.intersect(allowed))


def _lower_tongue(d):
    center, half = d.tongue_center_x, d.tongue_width / 2
    bottom = -d.height - d.tongue_projection
    shoulder = -d.height - min(0.3, d.tongue_projection / 2)
    inset = shoulder - bottom
    front = -d.entry_length - 14.374
    c1, r1 = (-d.entry_length + 11.6221, bottom + 6.4663), 6.4663
    c2, r2 = (-d.entry_length - 0.1546, -9.135), 9.17824

    def section(x, offset):
        radius1, radius2 = r1 - offset, r2 + offset
        j1, j2 = _circle_join(c1, radius1, c2, radius2)
        low = (c1[0], c1[1] - radius1)
        high = (c2[0] + sqrt(radius2 * radius2 - (-0.001 - c2[1]) ** 2), -0.001)

        def p(point):
            return (x, *point)

        return Wire(
            [
                _arc(p(low), p(_circle_mid(c1, low, j1, False)), p(j1)),
                _line(p(j1), p(j2)),
                _arc(p(j2), p(_circle_mid(c2, j2, high)), p(high)),
                _line(p(high), p((high[0], ROOT_OVERLAP))),
                _line(p((high[0], ROOT_OVERLAP)), p((0, ROOT_OVERLAP))),
                _line(p((0, ROOT_OVERLAP)), p((0, low[1]))),
                _line(p((0, low[1])), p(low)),
            ]
        )

    bevel = d.tongue_bevel
    stations = [
        (center - half, bevel),
        (center - half + bevel, 0),
        (center + half - bevel, 0),
        (center + half, bevel),
    ]
    tongue = Solid.make_loft([section(x, offset) for x, offset in stations], ruled=True)
    points = [
        (center - half, front, ROOT_OVERLAP),
        (center - half, front, shoulder),
        (center - half + inset, front, bottom),
        (center + half - inset, front, bottom),
        (center + half, front, shoulder),
        (center + half, front, ROOT_OVERLAP),
    ]
    tongue = _one(tongue.intersect(_prism(points, (0, -front + 1, 0))))

    # The same 45-degree bevel continues around both rear corners.
    def plan(z, inset):
        radius = d.tongue_rear_radius - inset
        xl, xr = center - half + inset, center + half - inset
        back, cy = -inset, -d.tongue_rear_radius
        lc, rc = (
            center - half + d.tongue_rear_radius,
            center + half - d.tongue_rear_radius,
        )

        def q(x, y):
            return (x, y, z)

        a, b, e, f, g, h = (
            q(xl, front),
            q(xr, front),
            q(xr, cy),
            q(rc, back),
            q(lc, back),
            q(xl, cy),
        )
        return Wire(
            [
                _line(a, b),
                _line(b, e),
                _arc(e, q(rc + radius / sqrt(2), cy + radius / sqrt(2)), f),
                _line(f, g),
                _arc(g, q(lc - radius / sqrt(2), cy + radius / sqrt(2)), h),
                _line(h, a),
            ]
        )

    envelope = Solid.make_loft(
        [plan(bottom, inset), plan(shoulder, 0), plan(ROOT_OVERLAP, 0)], ruled=True
    )
    return _one(tongue.intersect(envelope))


def lower_open_end_dovetail(d=LowerOpenDovetailDimensions()):
    """Left lower carrier, including its narrow projecting detent tongue."""
    return _one(_lower_carrier(d).fuse(_lower_tongue(d)))


def lower_central_dovetail(d=LowerOpenDovetailDimensions()):
    """Central carrier uses the same inner flank, mirrored about X=0."""
    body = _lower_carrier(d)
    cutter = Solid.make_box(50, d.entry_length + 20, d.height + 2).translate(
        (d.central_symmetry_x, -d.entry_length - 19, -d.height - 1)
    )
    half = _one(body.intersect(cutter)).translate((-d.central_symmetry_x, 0, 0))
    return _one(half.fuse(half.mirror(Plane.YZ)))


@dataclass(frozen=True)
class UpperRailDimensions(_PositiveDimensions):
    """Outer U rail; X=0 outer wall, Y=0 closed-end nose, skin Z=0."""

    width: float = 23.957
    height: float = 4.7
    crown_bevel: float = 0.96
    outer_rear_radius: float = 5.0
    inner_rear_radius: float = 1.5
    inner_turn_radius: float = 5.0
    inner_turn_setback: float = 11.0
    inner_wall_at_turn: float = 5.8348
    inner_wall_plan_angle: float = 2.0
    inner_wall_slope: float = 1.1111
    inner_wall_shoulder: float = 0.21
    long_leg_width: float = 3.0
    short_leg_ramp_radius: float = 7.0
    short_leg_ramp_slope: float = 1.1263
    crown_rise: float = 0.1157


def upper_outer_rail(d=UpperRailDimensions(), *, length: float = 168.1214):
    """Keep both end profiles fixed while changing the straight travel length."""
    if not isfinite(length) or length <= 60:
        raise ValueError("Upper rail length must be finite and greater than 60 mm")
    c = sqrt(0.5)
    back, width, height = length, d.width, d.height
    front = -13.0
    rleft, rright = d.outer_rear_radius, d.inner_rear_radius

    def p(x, y):
        return (x, y, -ROOT_OVERLAP)

    a, b, e, f, g, h = (
        p(0, front),
        p(width, front),
        p(width, back - rright),
        p(width - rright, back),
        p(rleft, back),
        p(0, back - rleft),
    )
    edges = [
        _line(a, b),
        _line(b, e),
        _arc(e, p(width - rright + rright * c, back - rright + rright * c), f),
        _line(f, g),
        _arc(g, p(rleft - rleft * c, back - rleft + rleft * c), h),
        _line(h, a),
    ]
    body = Solid.extrude(Face(Wire(edges)), (0, 0, height + ROOT_OVERLAP))
    top = [
        edge
        for edge in body.edges()
        if abs(edge.bounding_box().min.Z - height) < 1e-6
        and abs(edge.bounding_box().max.Z - height) < 1e-6
    ]
    body = body.chamfer(d.crown_bevel, None, top)
    # Three curved sections make the sloping inner wall, with an exact root band.
    turn = back - d.inner_turn_setback
    right, radius = width - d.long_leg_width + 0.003, d.inner_turn_radius
    taper = tan(radians(d.inner_wall_plan_angle))

    def inside(z, left):
        def q(x, y):
            return (x, y, z)

        a, b, e, f, g, h = (
            q(left - taper * (turn - front), front),
            q(left, turn),
            q(left + radius, turn + radius),
            q(right - radius, turn + radius),
            q(right, turn),
            q(right, front),
        )
        handle = radius * 0.52
        return Wire(
            [
                _line(a, b),
                Edge.make_bezier(
                    b,
                    q(left, turn + handle),
                    q(left + radius - handle, turn + radius),
                    e,
                ),
                _line(e, f),
                _arc(f, q(right - radius + radius * c, turn + radius * c), g),
                _line(g, h),
                _line(h, a),
            ]
        )

    left = d.inner_wall_at_turn
    sections = [
        inside(-2 * ROOT_OVERLAP, left),
        inside(d.inner_wall_shoulder, left),
        inside(
            height + ROOT_OVERLAP,
            left + (height + ROOT_OVERLAP - d.inner_wall_shoulder) * d.inner_wall_slope,
        ),
    ]
    body = _one(body.cut(Solid.make_loft(sections, ruled=True)))
    # The short outer leg has a planar lead-in followed by a circular crown blend.
    center = (back - 37.344, height - d.short_leg_ramp_radius + 0.006)
    radius, slope = d.short_leg_ramp_radius, d.short_leg_ramp_slope
    tangent = (
        center[0] - radius / sqrt(1 + slope * slope),
        center[1] + radius * slope / sqrt(1 + slope * slope),
    )
    start = (back - 45.2932 + slope * (-ROOT_OVERLAP - 0.001), -ROOT_OVERLAP)
    end = (center[0] - sqrt(radius * radius - (height - center[1]) ** 2), height)
    split = width - 6.5566

    def yz(point):
        return (-8, *point)

    edges = [
        _line(yz(start), yz(tangent)),
        _arc(yz(tangent), yz(_circle_mid(center, tangent, end, False)), yz(end)),
        _line(yz(end), yz((back + 4, height))),
        _line(yz((back + 4, height)), yz((back + 4, -ROOT_OVERLAP))),
        _line(yz((back + 4, -ROOT_OVERLAP)), yz(start)),
    ]
    envelope = Solid.extrude(Face(Wire(edges)), (split + 8, 0, 0)).fuse(
        Solid.make_box(width - split + 2, back - front + 5, height + 2).translate(
            (split, front, -1)
        )
    )
    body = _one(body.intersect(envelope))
    front_edges = []
    for edge in body.edges():
        bounds = edge.bounding_box()
        if (
            abs(bounds.min.X) < 1e-6
            and abs(bounds.max.X) < 1e-6
            and bounds.max.Y < back - 36
            and bounds.max.Z - bounds.min.Z > 0.1
        ):
            front_edges.append(edge)
    body = body.chamfer(d.crown_bevel, None, front_edges)

    # The long leg has two small circular nose rounds around a 45-degree step.
    def q(x, y):
        return (x, y, -1)

    a, b, e, f = (
        q(width, 0.5),
        q(width - 0.853553, 0.146447),
        q(width - d.long_leg_width + 0.292893, d.long_leg_width - 1),
        q(width - d.long_leg_width, d.long_leg_width - 0.292893),
    )
    edges = [
        _arc(a, q(width - 0.5, 0), b),
        _line(b, e),
        _arc(e, q(width - d.long_leg_width + 0.07612, d.long_leg_width - 0.675576), f),
        _line(f, q(width - d.long_leg_width, back + 4)),
        _line(q(width - d.long_leg_width, back + 4), q(width, back + 4)),
        _line(q(width, back + 4), a),
    ]
    nose = Solid.extrude(Face(Wire(edges)), (0, 0, height + 2)).fuse(
        Solid.make_box(split + 8, back - front + 5, height + 2).translate(
            (-8, front, -1)
        ),
        Solid.make_box(width + 16, back + 2, height + 2).translate((-8, 3.0214, -1)),
    )
    body = _one(body.intersect(nose))

    def yz(point):
        return (split, *point)

    lo, hi = -ROOT_OVERLAP, height
    points = [
        yz((0.979 * (lo - 0.001), lo)),
        yz((0.979 * (hi - 0.001), hi)),
        yz((back + 4, hi)),
        yz((back + 4, lo)),
    ]
    nose_ramp = _prism(points, (width - split + 2, 0, 0)).fuse(
        Solid.make_box(split + 8, back - front + 5, height + 2).translate(
            (-8, front, -1)
        )
    )
    body = _one(body.intersect(nose_ramp))
    # Keep the shallow crown pitch independent of module depth.
    crown_start = height - d.crown_rise
    crown_slope = d.crown_rise / (back - 2.0214)

    def crown(y):
        return crown_start + crown_slope * (y - 2.0214)

    points = [
        (-8, front, -1),
        (-8, back + 4, -1),
        (-8, back + 4, crown(back + 4)),
        (-8, front, crown(front)),
    ]
    return _one(body.intersect(_prism(points, (width + 16, 0, 0))))


@dataclass(frozen=True)
class TrackDimensions(_PositiveDimensions):
    """Shallow mechanical track, centered on XY with the sleeve skin at Z=0."""

    width: float = 7.5
    depth: float = 0.59827
    side_bevel: float = 0.4
    flat_length: float = 27.80255
    end_ramp_length: float = 16.72425


def upper_track_cutter(d=TrackDimensions()):
    """One shallow track with smooth end ramps and a bevel following its floor."""
    half_flat = d.flat_length / 2
    end = half_flat + d.end_ramp_length
    top = d.side_bevel + 1

    def section(x, lift):
        def q(y, z):
            return (x, y, z + lift)

        # Cubic ramps have horizontal tangents at the skin and the flat floor.
        a, b = q(-end, 0), q(-half_flat, -d.depth)
        c, e = q(half_flat, -d.depth), q(end, 0)
        edges = [
            Edge.make_bezier(
                a,
                q(-end + d.end_ramp_length / 3, 0),
                q(-half_flat - d.end_ramp_length / 3, -d.depth),
                b,
            ),
            _line(b, c),
            Edge.make_bezier(
                c,
                q(half_flat + d.end_ramp_length / 3, -d.depth),
                q(end - d.end_ramp_length / 3, 0),
                e,
            ),
            _line(e, (x, end, top)),
            _line((x, end, top), (x, -end, top)),
            _line((x, -end, top), a),
        ]
        return Wire(edges)

    half = d.width / 2
    wires = [
        section(-half, d.side_bevel),
        section(-half + d.side_bevel, 0),
        section(half - d.side_bevel, 0),
        section(half, d.side_bevel),
    ]
    return _one(Solid.make_loft(wires, ruled=True))
