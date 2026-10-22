"""Analytic alignment tabs and locking bridge, in reusable local coordinates.

No mesh/profile data is read at construction time. Module placement belongs to
connectors.py; every feature here attaches at its local Z=0 skin datum.
"""

from dataclasses import dataclass
from math import asin, atan, cos, sin, sqrt, pi, isfinite
from build123d import Edge, Face, Location, Plane, Solid, Wire


def _line(a, b):
    return Edge.make_line(a, b)


def _arc(center, radius, start, stop, plane="xy"):
    """Circular arc with angles in radians; coordinates may be XY, YZ or XZ."""

    def point(angle):
        a, b = center[0] + radius * cos(angle), center[1] + radius * sin(angle)
        if plane == "xy":
            return (a, b, 0)
        if plane == "yz":
            return (0, a, b)
        return (a, 0, b)

    return Edge.make_three_point_arc(
        point(start), point((start + stop) / 2), point(stop)
    )


def _one(shape):
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError("Expected one connected feature")
        shape = shape[0]
    solids = shape.solids()
    if len(solids) != 1 or not shape.is_valid:
        raise ValueError("Invalid analytic feature")
    return solids[0]


def _prism(points, direction):
    return Solid.extrude(Face(Wire.make_polygon(points)), direction)


@dataclass(frozen=True)
class UpperTabDimensions:
    """Capsule width, straight center spacing and 45-degree entry ramp."""

    width: float = 3.5
    center_length: float = 20.0
    height: float = 4.0
    ramp_start: float = 0.4
    root_overlap: float = 0.02

    def __post_init__(self):
        if not all(
            isfinite(value) and value > 0
            for value in (
                self.width,
                self.center_length,
                self.height,
                self.root_overlap,
            )
        ):
            raise ValueError("Upper tab dimensions must be positive and finite")
        if not isfinite(self.ramp_start) or self.ramp_start < 0:
            raise ValueError("Upper tab ramp_start must be finite and nonnegative")
        if self.height - self.ramp_start >= self.center_length + self.width:
            raise ValueError("Upper tab ramp must leave material at the crown")


def upper_alignment_tab(d=UpperTabDimensions()):
    """Capsule tab; front semicircle center is (0,0), skin at Z=0."""
    r, length = d.width / 2, d.center_length
    edges = [
        _arc((0, 0), r, pi, 2 * pi),
        _line((r, 0, 0), (r, length, 0)),
        _arc((0, length), r, 0, pi),
        _line((-r, length, 0), (-r, 0, 0)),
    ]
    body = Solid.extrude(Face(Wire(edges)), (0, 0, d.height + d.root_overlap))
    body = body.moved(Location((0, 0, -d.root_overlap)))
    # The front 45-degree ramp starts at its independently specified height.
    z0, z1 = -d.root_overlap - 1, d.height + 1
    y0, y1 = -r + z0 - d.ramp_start, -r + z1 - d.ramp_start
    front = min(-r, y0, y1) - 1
    cutter = _prism(
        [
            (-d.width, front, z0),
            (-d.width, y0, z0),
            (-d.width, y1, z1),
            (-d.width, front, z1),
        ],
        (2 * d.width, 0, 0),
    )
    return _one(body.cut(cutter))


@dataclass(frozen=True)
class LowerTabDimensions:
    """Wedge length, taper, skin rolls and longitudinal tip rounds."""

    width: float = 3.5
    height: float = 5.2
    front_at_skin: float = 4.4148
    rear_at_skin: float = 18.13655
    taper: float = 0.96153846
    front_root_radius: float = 3.0
    rear_root_radius: float = 2.0
    tip_radius: float = 0.85
    root_overlap: float = 0.02

    def __post_init__(self):
        if not all(isfinite(value) and value > 0 for value in vars(self).values()):
            raise ValueError("Lower tab dimensions must be positive and finite")
        if self.width <= 2 * self.tip_radius or self.height <= self.tip_radius:
            raise ValueError(
                "Lower tab tip radius must fit within its width and height"
            )
        if self.rear_at_skin - self.front_at_skin <= 2 * self.taper * self.height:
            raise ValueError("Lower tab taper must leave a positive length at the tip")
        tangent_drop = 1 - sin(atan(self.taper))
        if (
            self.height
            <= max(self.front_root_radius, self.rear_root_radius) * tangent_drop
        ):
            raise ValueError("Lower tab root rolls must finish above the tip")


def lower_alignment_tab(d=LowerTabDimensions()):
    """Rounded wedge; width centered on X=0 and sleeve attachment at Z=0."""
    angle = atan(d.taper)

    def root_center(intercept, radius, front):
        # Circle tangent to the skin and the sloping planar end.
        offset = d.taper * radius - radius * sqrt(1 + d.taper * d.taper)
        return intercept + offset * (1 if front else -1), -radius

    front = root_center(d.front_at_skin, d.front_root_radius, True)
    rear = root_center(d.rear_at_skin, d.rear_root_radius, False)

    def yz(y, z):
        return (0, y, z)

    front_top, rear_top = yz(front[0], 0), yz(rear[0], 0)
    front_tangent = yz(
        front[0] + d.front_root_radius * cos(angle),
        front[1] + d.front_root_radius * sin(angle),
    )
    rear_tangent = yz(
        rear[0] - d.rear_root_radius * cos(angle),
        rear[1] + d.rear_root_radius * sin(angle),
    )
    front_tip = yz(d.front_at_skin + d.taper * d.height, -d.height)
    rear_tip = yz(d.rear_at_skin - d.taper * d.height, -d.height)
    edges = [
        _line(yz(front[0], d.root_overlap), front_top),
        _arc(front, d.front_root_radius, pi / 2, angle, "yz"),
        _line(front_tangent, front_tip),
        _line(front_tip, rear_tip),
        _line(rear_tip, rear_tangent),
        _arc(rear, d.rear_root_radius, pi - angle, pi / 2, "yz"),
        _line(rear_top, yz(rear[0], d.root_overlap)),
        _line(yz(rear[0], d.root_overlap), yz(front[0], d.root_overlap)),
    ]
    body = Solid.extrude(Face(Wire(edges)), (d.width, 0, 0))
    body = body.moved(Location((-d.width / 2, 0, 0)))
    # Round only the two longitudinal bottom edges; end slopes remain planar.
    half, radius = d.width / 2, d.tip_radius
    center_z = -d.height + radius
    left, right = (-half + radius, center_z), (half - radius, center_z)
    edges = [
        _line((-half, 0, d.root_overlap), (-half, 0, center_z)),
        _arc(left, radius, pi, 1.5 * pi, "xz"),
        _line((-half + radius, 0, -d.height), (half - radius, 0, -d.height)),
        _arc(right, radius, 1.5 * pi, 2 * pi, "xz"),
        _line((half, 0, center_z), (half, 0, d.root_overlap)),
        _line((half, 0, d.root_overlap), (-half, 0, d.root_overlap)),
    ]
    start_y, end_y = front[0] - 1, rear[0] + 1
    envelope = Solid.extrude(Face(Wire(edges)), (0, end_y - start_y, 0))
    envelope = envelope.moved(Location((0, start_y, 0)))
    return _one(body.intersect(envelope))


@dataclass(frozen=True)
class LockingBridgeDimensions:
    """Coupled bend, width and ramp controls for a symmetric spring bridge.

    Module sizing moves this fixed mating section. Its local shape controls
    must leave the crown above both ramp transitions and inside the entry roll.
    """

    height: float = 4.7
    inner_half_width: float = 38.3057
    outer_corner_x: float = 38.85
    rear_y: float = 65.7364
    outer_corner_radius: float = 5.0
    inner_corner_radius: float = 2.9
    arm_lobe_center_x: float = 30.4062
    arm_lobe_y: float = 60.481
    arm_lobe_radius: float = 3.0
    arm_turn_center_x: float = 32.3105
    arm_turn_y: float = 50.091
    arm_turn_radius: float = 3.0
    arm_tip_center_x: float = 33.0105
    arm_tip_y: float = 49.8173
    arm_tip_radius: float = 2.3
    center_blend_x: float = 16.7672
    center_blend_radius: float = 5.0
    neck_half_width: float = 40.16
    neck_height: float = 0.5
    neck_radius: float = 0.7
    crown_half_width: float = 43.75
    crown_radius: float = 0.55
    front_at_skin: float = 10.9327
    front_slope: float = 1.0416666667
    front_crown_radius: float = 2.0
    front_crown_center_height: float = 2.8
    arm_ramp_at_skin: float = 47.5162
    arm_ramp_slope: float = 1 + sqrt(2)
    root_overlap: float = 0.02

    def __post_init__(self):
        if not all(isfinite(value) and value > 0 for value in vars(self).values()):
            raise ValueError("Locking bridge dimensions must be positive and finite")
        if self.neck_height >= self.neck_radius:
            raise ValueError("Bridge neck radius must exceed its center height")
        if not self.inner_half_width < self.neck_half_width < self.crown_half_width:
            raise ValueError("Bridge inner, neck and crown half-widths must increase")
        if self.crown_half_width > self.outer_corner_x + self.outer_corner_radius:
            raise ValueError("Bridge crown must fit inside its outside plan outline")
        if self.arm_lobe_center_x + self.inner_corner_radius >= self.inner_half_width:
            raise ValueError("Bridge inner corner must leave room for the spring lobe")
        if self.arm_lobe_y + self.arm_lobe_radius >= self.rear_y:
            raise ValueError("Bridge spring lobe must leave material at the rear")
        neck_intercept = (
            self.neck_half_width
            + self.neck_radius
            - self.neck_height
            - self.neck_radius * sqrt(2)
        )
        crown_center_z = (
            self.crown_half_width
            - self.crown_radius
            + self.crown_radius * sqrt(2)
            - neck_intercept
        )
        entry_tangent_z = (
            self.front_crown_center_height
            + self.front_crown_radius * self.front_slope / sqrt(1 + self.front_slope**2)
        )
        entry_top_z = self.front_crown_center_height + self.front_crown_radius
        if not max(crown_center_z, entry_tangent_z) < self.height <= entry_top_z:
            raise ValueError(
                "Bridge height, crown widths and entry roll are coupled: crown "
                "height must lie above both transitions and within the entry circle"
            )


def _bridge_outline(d):
    """One half of a rounded XY spring outline, mirrored across its center."""
    inner = d.inner_half_width
    back = d.rear_y - d.outer_corner_radius
    corner = (
        -inner + d.inner_corner_radius,
        d.arm_lobe_y + d.arm_lobe_radius - d.inner_corner_radius,
    )
    lobe = (-d.arm_lobe_center_x, d.arm_lobe_y)
    turn = (-d.arm_turn_center_x, d.arm_turn_y)
    tip = (-d.arm_tip_center_x, d.arm_tip_y)
    blend = (-d.center_blend_x, back - d.center_blend_radius)

    def point(c, r, a):
        return (c[0] + r * cos(a), c[1] + r * sin(a), 0)

    bottom = (-inner, 0, 0)
    segments = [
        _line(bottom, (-inner, corner[1], 0)),
        _arc(corner, d.inner_corner_radius, pi, pi / 2),
        _line(
            point(corner, d.inner_corner_radius, pi / 2),
            point(lobe, d.arm_lobe_radius, pi / 2),
        ),
        _arc(lobe, d.arm_lobe_radius, pi / 2, -pi / 4),
        _line(
            point(lobe, d.arm_lobe_radius, -pi / 4),
            point(turn, d.arm_turn_radius, 3 * pi / 4),
        ),
        _arc(turn, d.arm_turn_radius, 3 * pi / 4, pi),
        _line(point(turn, d.arm_turn_radius, pi), point(tip, d.arm_tip_radius, pi)),
        _arc(tip, d.arm_tip_radius, pi, 7 * pi / 4),
        _line(
            point(tip, d.arm_tip_radius, 7 * pi / 4),
            point(blend, d.center_blend_radius, 3 * pi / 4),
        ),
        _arc(blend, d.center_blend_radius, 3 * pi / 4, pi / 2),
    ]
    edges = segments + [edge.mirror(Plane.YZ) for edge in segments]
    edges.append(
        _line(point(blend, d.center_blend_radius, pi / 2), (d.center_blend_x, back, 0))
    )
    outside = d.outer_corner_x + d.outer_corner_radius
    for side in (-1, 1):
        edges.append(_line((side * inner, 0, 0), (side * outside, 0, 0)))
        edges.append(_line((side * outside, 0, 0), (side * outside, back, 0)))
    edges.extend(
        [
            _arc((d.outer_corner_x, back), d.outer_corner_radius, 0, pi / 2),
            _line((d.outer_corner_x, d.rear_y, 0), (-d.outer_corner_x, d.rear_y, 0)),
            _arc((-d.outer_corner_x, back), d.outer_corner_radius, pi / 2, pi),
        ]
    )
    return Face(Wire.combine(edges)[0])


def _bridge_width_envelope(d):
    c = d.neck_half_width + d.neck_radius
    start = pi + asin(d.neck_height / d.neck_radius)
    xroot = c - sqrt(d.neck_radius * d.neck_radius - d.neck_height * d.neck_height)
    tangent = (c - d.neck_radius / sqrt(2), d.neck_height + d.neck_radius / sqrt(2))
    intercept = tangent[0] - tangent[1]
    tc = d.crown_half_width - d.crown_radius
    th = tc + d.crown_radius * sqrt(2) - intercept
    top_tangent = (tc + d.crown_radius / sqrt(2), th - d.crown_radius / sqrt(2))
    right = [
        _line((xroot, 0, -d.root_overlap), (xroot, 0, 0)),
        _arc((c, d.neck_height), d.neck_radius, start, 3 * pi / 4, "xz"),
        _line((tangent[0], 0, tangent[1]), (top_tangent[0], 0, top_tangent[1])),
        _arc((tc, th), d.crown_radius, -pi / 4, 0, "xz"),
        _line((d.crown_half_width, 0, th), (d.crown_half_width, 0, d.height)),
    ]
    edges = right + [edge.mirror(Plane.YZ) for edge in right]
    edges.extend(
        [
            _line((-xroot, 0, -d.root_overlap), (xroot, 0, -d.root_overlap)),
            _line(
                (-d.crown_half_width, 0, d.height), (d.crown_half_width, 0, d.height)
            ),
        ]
    )
    return Solid.extrude(Face(Wire.combine(edges)[0]), (0, d.rear_y + 1, 0))


def _bridge_front_envelope(d):
    slope = d.front_slope
    r = d.front_crown_radius
    cz = d.front_crown_center_height
    cy = d.front_at_skin + slope * cz + r * sqrt(1 + slope * slope)
    a = pi - atan(slope)
    b = pi - asin((d.height - cz) / r)
    tangent = (cy + r * cos(a), cz + r * sin(a))
    top = (cy + r * cos(b), d.height)
    end = d.rear_y + 1
    edges = [
        _line((0, d.front_at_skin, -d.root_overlap), (0, d.front_at_skin, 0)),
        _line((0, d.front_at_skin, 0), (0, *tangent)),
        _arc((cy, cz), r, a, b, "yz"),
        _line((0, *top), (0, end, d.height)),
        _line((0, end, d.height), (0, end, -d.root_overlap)),
        _line((0, end, -d.root_overlap), (0, d.front_at_skin, -d.root_overlap)),
    ]
    return Solid.extrude(Face(Wire(edges)), (2 * d.crown_half_width + 2, 0, 0)).moved(
        Location((-d.crown_half_width - 1, 0, 0))
    )


def upper_closed_end_locking_bridge(d=LockingBridgeDimensions()):
    """Symmetric spring bridge, with its skin attachment at Z=0.

    Circular XY bends are extruded once. Two envelopes create the rail taper
    and leading ramp; a final planar cut creates the two opposed spring ramps.
    """
    body = Solid.extrude(_bridge_outline(d), (0, 0, d.height + d.root_overlap)).moved(
        Location((0, 0, -d.root_overlap))
    )
    body = _one(body.intersect(_bridge_width_envelope(d)))
    body = _one(body.intersect(_bridge_front_envelope(d)))
    # Cut only the spring arms, leaving the long side rails intact.
    half = d.inner_half_width - d.inner_corner_radius / 2
    z0, z1 = -d.root_overlap - 1, d.height + 1
    y0 = d.arm_ramp_at_skin + d.arm_ramp_slope * z0
    y1 = d.arm_ramp_at_skin + d.arm_ramp_slope * z1
    cutter = _prism(
        [(-half, 0, z0), (-half, y0, z0), (-half, y1, z1), (-half, 0, z1)],
        (2 * half, 0, 0),
    )
    return _one(body.cut(cutter))
