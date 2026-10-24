"""Native S/M/L geared locking rails, reconstructed from the supplied rails.

The two purchased parts share a beveled rack and rounded ends. The retained
rail adds a rounded longitudinal rib on its back. Construction uses editable
dimensions, circular arcs and cubic tip blends; it never reads the reference
mesh. Local X follows the rack, +Y points toward the teeth, and Z=0 is the
flat print bed. The source is a print layout, not an assembly registration.
"""

from dataclasses import dataclass, fields, replace
from math import asin, cos, isfinite, pi, sin, sqrt

from build123d import Compound, Edge, Face, Solid, Wire

from .spec import FAMILIES


@dataclass(frozen=True)
class GearRailSpec:
    family: str = "S"

    def __post_init__(self):
        if self.family not in ("S", "M", "L"):
            raise ValueError("Geared rails support S, M, and L families")

    @property
    def slug(self):
        return f"{self.family.lower()}_geared_rails"

    @property
    def name(self):
        return f"{self.family} Geared Rails"


@dataclass(frozen=True)
class GearRailDimensions:
    """Measured design dimensions in mm, with the printed cross-section explicit.

    Three valleys in the supplied model are 0.09 mm narrower; preserving them
    also preserves the cumulative tooth phase. ``tooth_pitch`` is the normal
    valley-to-valley interval before that local shortening. Small source mesh
    ripples (under 0.02 mm) are replaced with nominal planes and native curves.
    """

    length: float = 121.0537
    width: float = 4.8
    thickness: float = 3.8
    edge_bevel: float = 0.8
    first_valley_center: float = 37.89
    tooth_pitch: float = 4.02124
    tooth_count: int = 20
    root_radius: float = 0.96
    root_floor: float = 1.92
    valley_width: float = 2.1
    narrow_valley_reduction: float = 0.09
    narrow_valleys: tuple[int, ...] = (1, 11, 13)
    flank_shoulder: float = 3.2747
    tail_width: float = 2.69
    tail_taper_start: float = 115.8945
    tail_taper_slope: float = 0.40076
    retaining_projection: float = 1.4187
    retaining_radius: float = 0.8
    retaining_start: float = 9.209
    retaining_full_start: float = 15.6543
    retaining_full_end: float = 105.7451
    retaining_end: float = 112.1914
    extended_tail: bool = False
    tail_corner_radius: float = 0.4
    tail_relief_radius: float = 1.7

    def __post_init__(self):
        for field in fields(self):
            if field.name in {"tooth_count", "narrow_valleys", "extended_tail"}:
                continue
            value = getattr(self, field.name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field.name} must be finite and positive")
        if type(self.tooth_count) is not int or self.tooth_count < 1:
            raise ValueError("tooth_count must be a positive integer")
        if type(self.extended_tail) is not bool:
            raise ValueError("extended_tail must be a boolean")
        if any(type(i) is not int or not 0 <= i < self.tooth_count for i in self.narrow_valleys):
            raise ValueError("narrow_valleys must contain valid tooth indices")
        if len(set(self.narrow_valleys)) != len(self.narrow_valleys):
            raise ValueError("narrow_valleys cannot repeat a tooth index")
        if not 0 < self.edge_bevel < min(self.width, self.thickness) / 2:
            raise ValueError("edge_bevel must leave a flat central section")
        if self.valley_width - self.narrow_valley_reduction < 2 * self.root_radius:
            raise ValueError("root radii must fit the narrow valleys")
        if not self.root_floor + self.root_radius < self.flank_shoulder < self.width - .3:
            raise ValueError("root and flank dimensions must fit below the tooth tips")
        if not 0 < self.retaining_start < self.retaining_full_start < self.retaining_full_end < self.retaining_end < self.length:
            raise ValueError("retaining rib stations must increase along the rack")
        if self.retaining_radius > self.retaining_projection:
            raise ValueError("retaining round must fit its projection")
        if self.thickness <= 2 * (self.edge_bevel + self.retaining_radius):
            raise ValueError("retaining rounds must leave a central flat")
        if self.tail_taper_start >= self.length:
            raise ValueError("tail taper must start before the end")
        if self.thickness - self.tail_taper_slope * (self.length - self.tail_taper_start) <= 0:
            raise ValueError("tail taper must leave material at the tip")
        if self.valley_centers[-1] + self.valley_width / 2 >= self.length - self.tail_width / 2:
            raise ValueError("teeth must leave room for the rounded tail")
        if self.extended_tail:
            if self.tail_corner_radius + self.tail_relief_radius > self.width - self.tail_width:
                raise ValueError("tail relief rounds must fit the width transition")
            if self.tail_taper_start - self.tail_corner_radius - self.tail_relief_radius <= self.valley_centers[-1] + self.valley_width / 2 + .75:
                raise ValueError("extended tail must start beyond the final tooth")

    @property
    def valley_centers(self):
        return tuple(
            self.first_valley_center + i * self.tooth_pitch
            - self.narrow_valley_reduction * (
                sum(j < i for j in self.narrow_valleys) + .5 * (i in self.narrow_valleys)
            ) for i in range(self.tooth_count)
        )


SPEC = GearRailSpec()
D = GearRailDimensions()


def rail_dimensions(family="S"):
    """Move the tail to match width while retaining the source tooth mechanism.

    Source M/L rails add half the module width difference after the 20th tooth.
    Their teeth, nose and retaining rib are identical to S. A full-width shank
    joins the same tapered tip through R0.4/R1.7 rounds. Rail size depends only
    on family, not drawer depth or tier count.
    """
    spec = GearRailSpec(family)
    extension = (FAMILIES[spec.family].width - FAMILIES["S"].width) / 2
    if not extension:
        return D
    return replace(D, length=D.length + extension,
                   tail_taper_start=D.tail_taper_start + extension,
                   extended_tail=True)


def _one(shape):
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError("A gear rail must be connected")
        shape = shape[0]
    if not shape.is_valid or len(shape.solids()) != 1:
        raise ValueError("Invalid native gear rail")
    return shape.solids()[0]


def _line(a, b):
    return Edge.make_line(a, b)


def _arc(a, m, b):
    return Edge.make_three_point_arc(a, m, b)


def _plan(d):
    """One analytic rack silhouette, before thickness bevels and tail ramp."""
    def p(x, y):
        return (x, y, 0)

    edges = []
    nose_radius = d.width / 2
    last = p(nose_radius, d.width)
    root_y = d.root_floor + d.root_radius
    c = sqrt(.5)
    for index, center in enumerate(d.valley_centers):
        valley = d.valley_width - d.narrow_valley_reduction * (index in d.narrow_valleys)
        left, right = center - valley / 2, center + valley / 2
        # Measured 20-degree flanks meet a short root fillet, then the R.96
        # quarter circles forming the bottom. The .18/.09 flat is intentional.
        start = p(left - .75, d.width)
        tip = p(left - .465, d.width - .1696)
        flank = p(left - .0314, d.flank_shoulder + .1660)
        shoulder = p(left, d.flank_shoulder)
        root = p(left, root_y)
        floor_left = p(left + d.root_radius, d.root_floor)
        floor_right = p(right - d.root_radius, d.root_floor)
        root_right = p(right, root_y)
        edges.extend([
            _line(last, start),
            Edge.make_bezier(start, p(left - .605, d.width),
                             p(left - .5014, d.width - .0696), tip),
            _line(tip, flank),
            _arc(flank, p(left - .0076, d.flank_shoulder + .084), shoulder),
            _line(shoulder, root),
            _arc(root, p(left + d.root_radius * (1 - c), root_y - d.root_radius * c), floor_left),
            _line(floor_left, floor_right),
        ])
        if index == d.tooth_count - 1 and not d.extended_tail:
            # The final root blends directly into the lower tail, without
            # another tooth. Stop the circular quadrant at the tail height.
            delta = d.tail_width - root_y
            end = p(right - d.root_radius + sqrt(d.root_radius**2 - delta**2), d.tail_width)
            middle_angle = (-pi / 2 + asin(delta / d.root_radius)) / 2
            middle = p(right - d.root_radius + d.root_radius * cos(middle_angle),
                       root_y + d.root_radius * sin(middle_angle))
            edges.append(_arc(floor_right, middle, end))
            last = end
        else:
            shoulder_right = p(right, d.flank_shoulder)
            flank_right = p(right + .0314, d.flank_shoulder + .1660)
            tip_right = p(right + .465, d.width - .1696)
            end = p(right + .75, d.width)
            edges.extend([
                _arc(floor_right, p(right - d.root_radius * (1 - c), root_y - d.root_radius * c), root_right),
                _line(root_right, shoulder_right),
                _arc(shoulder_right, p(right + .0076, d.flank_shoulder + .084), flank_right),
                _line(flank_right, tip_right),
                Edge.make_bezier(tip_right, p(right + .5014, d.width - .0696),
                                 p(right + .605, d.width), end),
            ])
            last = end

    if d.extended_tail:
        # The larger source rails retain exactly twenty teeth, then add a
        # full-width shank. Two tangent rounds lower it to the original tip.
        outer, inner = d.tail_corner_radius, d.tail_relief_radius
        start_x = d.tail_taper_start - outer - inner
        shoulder_y = d.tail_width + inner
        start = p(start_x, d.width)
        corner_end = p(start_x + outer, d.width - outer)
        shoulder = p(start_x + outer, shoulder_y)
        end = p(d.tail_taper_start, d.tail_width)
        edges.extend([
            _line(last, start),
            _arc(start, p(start_x + outer*c, d.width - outer + outer*c), corner_end),
            _line(corner_end, shoulder),
            _arc(shoulder, p(d.tail_taper_start - inner*c, shoulder_y - inner*c), end),
        ])
        last = end

    # A long R3 roll meets the rounded tip, retaining the measured tail outline.
    tail_shift = d.length - 121.0537
    tail_top = p(119.3926 + tail_shift, d.tail_width)
    tail_join = p(120.2246 + tail_shift, d.tail_width - .1176)
    tail_bottom = p(d.length - d.tail_width / 2, 0)
    edges.extend([
        _line(last, tail_top),
        _arc(tail_top, p(119.812 + tail_shift, d.tail_width - .0294), tail_join),
        _arc(tail_join, p(d.length, d.tail_width / 2), tail_bottom),
        _line(tail_bottom, p(nose_radius, 0)),
        _arc(p(nose_radius, 0), p(0, nose_radius), p(nose_radius, d.width)),
    ])
    return Face(Wire(edges))


def _retaining_rib(d):
    """Rounded back rib with the original tapered insertion ends."""
    r, projection = d.retaining_radius, d.retaining_projection
    low, high = d.edge_bevel - .0078, d.thickness - d.edge_bevel + .0078
    center_y = -projection + r
    def p(y, z):
        return (0, y, z)
    c = sqrt(.5)
    edges = [
        _line(p(.02, low), p(center_y, low)),
        _arc(p(center_y, low), p(center_y-r*c, low+r-r*c), p(-projection, low+r)),
        _line(p(-projection, low+r), p(-projection, high-r)),
        _arc(p(-projection, high-r), p(center_y-r*c, high-r+r*c), p(center_y, high)),
        _line(p(center_y, high), p(.02, high)),
        _line(p(.02, high), p(.02, low)),
    ]
    rib = Solid.extrude(Face(Wire(edges)), (d.length, 0, 0))
    plan = Face(Wire.make_polygon([
        (d.retaining_start, .02, -1), (d.retaining_full_start, -projection, -1),
        (d.retaining_full_end, -projection, -1), (d.retaining_end, .02, -1),
    ]))
    return _one(rib.intersect(Solid.extrude(plan, (0, 0, d.thickness + 2))))


def build_gear_rail(retained=False, dimensions=None, *, spec=SPEC):
    """Build either single rail, lying flat on Z=0 for printing.

    ``retained=True`` selects the extra back rib. The cross-section dimensions
    are nominal source dimensions; mating part clearances belong to the box
    and module. The default body is 4.8 mm wide and 3.8 mm thick.
    """
    d = rail_dimensions(spec.family) if dimensions is None else dimensions
    body = Solid.extrude(_plan(d), (0, 0, d.thickness))
    b, w, h = d.edge_bevel, d.width, d.thickness
    cross = Face(Wire.make_polygon([
        (-1, b, 0), (-1, w-b, 0), (-1, w, b), (-1, w, h-b),
        (-1, w-b, h), (-1, b, h), (-1, 0, h-b), (-1, 0, b),
    ]))
    body = _one(body.intersect(Solid.extrude(cross, (d.length + 2, 0, 0))))
    # The tail ramp is a plane, not a smooth bend in the purchased model.
    end_height = h - d.tail_taper_slope * (d.length + 1 - d.tail_taper_start)
    ramp = Face(Wire.make_polygon([
        (-1, -2, -1), (d.length+1, -2, -1), (d.length+1, -2, end_height),
        (d.tail_taper_start, -2, h), (-1, -2, h),
    ]))
    body = _one(body.intersect(Solid.extrude(ramp, (0, d.width + 4, 0))))
    if retained:
        body = _one(body.fuse(_retaining_rib(d)))
    body.label = f"{spec.family} geared rail — {'retained' if retained else 'plain'}"
    return body


def build_geared_rails(dimensions=None, *, spec=SPEC):
    """Both native rails in a print layout with a 5 mm separation."""
    dimensions = rail_dimensions(spec.family) if dimensions is None else dimensions
    retained = build_gear_rail(True, dimensions, spec=spec).translate((0, dimensions.retaining_projection, 0))
    plain = build_gear_rail(False, dimensions, spec=spec).translate((0, dimensions.retaining_projection + dimensions.width + 5, 0))
    return Compound(label=spec.name, children=[retained, plain])
