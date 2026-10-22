"""Constructive shell envelope with smooth corners and mirrored front ears.

Four tangent circular arcs describe each body corner. Circular rolls, straight
ramps and bevels describe the front ears. These replace the measured polygon
loft while retaining fixed feature sizes as the module grows.
"""
from dataclasses import dataclass
from math import atan, cos, sin, sqrt, pi, isfinite
from build123d import Edge, Wire, Face, Solid, Plane
from .spec import ModuleSpec, DEFAULT_SPEC


@dataclass(frozen=True)
class EnvelopeDimensions:
    """Fixed corner and ear sections; ModuleSpec controls the box size.

    Corner spans, radii and tangent angles are coupled shape controls. They
    must leave positive radii for the final two tangent arcs.
    """

    corner_width: float = 15.4004
    corner_height: float = 12.0
    corner_first_radius: float = 21.26160934
    corner_second_radius: float = 8.06525726
    corner_turns: tuple[float, float, float] = (.26136433, 1.28685352, 1.54322728)
    ear_back_offset: float = 69.0
    ear_front_offset: float = 12.0
    ear_front_radius: float = 5.0
    ear_front_clip: float = .04
    ear_bevel: float = .96
    ear_lower_radius: float = 7.0
    ear_slope: float = 8 / 9
    ear_upper_start_drop: float = 11.67
    ear_lower_anchor_offset: float = 63.1
    ear_lower_anchor_height: float = 11.142

    def __post_init__(self):
        positive = (self.corner_width, self.corner_height,
                    self.corner_first_radius, self.corner_second_radius)
        if not all(isfinite(value) and value > 0 for value in positive):
            raise ValueError('Corner width, height and radii must be positive and finite')
        angles = self.corner_turns
        if (len(angles) != 3 or not all(isfinite(value) for value in angles)
                or not 0 < angles[0] < angles[1] < angles[2] < pi / 2):
            raise ValueError('Corner tangent angles must satisfy 0 < first < second < third < pi/2')
        radii = _corner_radii(self)
        if not all(isfinite(radius) and radius > 0 for radius in radii):
            raise ValueError(
                'Corner spans, radii and angles are coupled: these values give a '
                'nonpositive derived arc radius. Use ModuleSpec to change box size.')


def _corner_radii(dimensions):
    """Solve the last two radii so the tangent arcs reach both corner spans."""
    first, second, third = dimensions.corner_turns
    first_radius = dimensions.corner_first_radius
    second_radius = dimensions.corner_second_radius
    remaining_x = (dimensions.corner_width - first_radius * (1 - cos(first))
                   - second_radius * (cos(first) - cos(second)))
    remaining_z = (dimensions.corner_height - first_radius * sin(first)
                   - second_radius * (sin(second) - sin(first)))
    a, b = cos(second) - cos(third), cos(third)
    c, d = sin(third) - sin(second), 1 - sin(third)
    determinant = a * d - b * c
    if abs(determinant) < 1e-14:
        raise ValueError('Corner tangent angles are too close to solve the coupled arc radii')
    third_radius = (remaining_x * d - b * remaining_z) / determinant
    fourth_radius = (a * remaining_z - remaining_x * c) / determinant
    return first_radius, second_radius, third_radius, fourth_radius


def _corner_arcs(spec, dimensions):
    """Four tangent arcs with exact vertical and horizontal end tangencies."""
    first, second, third = dimensions.corner_turns
    radii = _corner_radii(dimensions)
    angles = [0, first, second, third, pi / 2]
    start = (spec.half_width, spec.height - dimensions.corner_height)
    arcs = []
    for radius, start_angle, end_angle in zip(radii, angles, angles[1:]):
        center = (start[0] - radius * cos(start_angle), start[1] - radius * sin(start_angle))
        point = lambda angle: (center[0] + radius * cos(angle), center[1] + radius * sin(angle))
        end = point(end_angle)
        arcs.append([start, point((start_angle + end_angle) / 2), end])
        start = end
    return arcs


def _smooth_sleeve(spec, dimensions):
    """The upper-right quarter defines all four reflected body corners."""
    upper = _corner_arcs(spec, dimensions)
    corners = []
    for side, top in [(1, True), (-1, True), (-1, False), (1, False)]:
        arcs = [[(side * x, 0, z if top else spec.height - z) for x, z in arc]
                for arc in upper]
        if (side == -1) == top:
            arcs = [list(reversed(arc)) for arc in reversed(arcs)]
        corners.append(arcs)
    edges = []
    for index, arcs in enumerate(corners):
        edges.extend(Edge.make_three_point_arc(*arc) for arc in arcs)
        edges.append(Edge.make_line(arcs[-1][-1], corners[(index + 1) % 4][0][0]))
    return Solid.extrude(Face(Wire(edges)), (0, spec.depth, 0))


def _right_ear(spec, dimensions):
    """Straight ramps, a lower R7 roll, .96 bevel and R5 front corner."""
    outer_x = spec.half_width
    inner_x = outer_x - dimensions.corner_width
    back = spec.depth - dimensions.ear_back_offset
    front = spec.depth - dimensions.ear_front_offset
    slope, bevel = dimensions.ear_slope, dimensions.ear_bevel
    normal_height = bevel * sqrt(1 + slope * slope)
    upper_back = spec.height - dimensions.ear_upper_start_drop + normal_height
    lower_anchor = spec.depth - dimensions.ear_lower_anchor_offset
    lower_z = dimensions.ear_lower_anchor_height - normal_height
    intersection_y = lower_anchor + lower_z / slope
    angle = atan(slope)
    radius = dimensions.ear_lower_radius
    center_y = intersection_y + radius * sin(angle) / (1 + cos(angle))
    tangent = (center_y - radius * sin(angle), radius - radius * cos(angle))
    lower_back = lower_z + slope * (lower_anchor - back)
    upper_front = upper_back + slope * (front - back)
    point = lambda yz: (inner_x, *yz)
    lower_mid = (center_y - radius * sin(angle / 2), radius - radius * cos(angle / 2))
    edges = [
        Edge.make_line(point((back, lower_back)), point(tangent)),
        Edge.make_three_point_arc(point(tangent), point(lower_mid), point((center_y, 0))),
        Edge.make_line(point((center_y, 0)), point((front, 0))),
        Edge.make_line(point((front, 0)), point((front, upper_front))),
        Edge.make_line(point((front, upper_front)), point((back, upper_back))),
        Edge.make_line(point((back, upper_back)), point((back, lower_back))),
    ]
    ear = Solid.extrude(Face(Wire(edges)), (dimensions.corner_width, 0, 0))
    bevel_edges = []
    for edge in ear.edges():
        bounds = edge.bounding_box()
        on_outside = abs(bounds.min.X - outer_x) < 1e-6 and abs(bounds.max.X - outer_x) < 1e-6
        if on_outside and bounds.size.Y > 1e-6:
            bevel_edges.append(edge)
    ear = ear.chamfer(bevel, None, bevel_edges)

    # Continue the bottom bevel around the rounded plan footprint and front cap.
    circle_x = outer_x - (dimensions.ear_front_radius - dimensions.ear_front_clip)
    circle_y = front - dimensions.ear_front_radius

    def footprint_wire(inset, z):
        radius = dimensions.ear_front_radius - inset
        outer = outer_x - inset
        arc_start = circle_y + sqrt(radius**2 - (outer - circle_x)**2)
        angle = atan((arc_start - circle_y) / (outer - circle_x))
        middle = (angle + pi / 2) / 2
        points = [
            (inner_x, back, z), (outer, back, z), (outer, arc_start, z),
            (circle_x, front - inset, z), (inner_x, front - inset, z),
        ]
        midpoint = (circle_x + radius * cos(middle), circle_y + radius * sin(middle), z)
        return Wire([
            Edge.make_line(points[0], points[1]),
            Edge.make_line(points[1], points[2]),
            Edge.make_three_point_arc(points[2], midpoint, points[3]),
            Edge.make_line(points[3], points[4]),
            Edge.make_line(points[4], points[0]),
        ])

    lower = footprint_wire(bevel, 0)
    upper = footprint_wire(0, bevel)
    bevel_solid = Solid.make_loft([lower, upper], ruled=True)
    prism = Solid.extrude(Face(upper), (0, 0, spec.height + 100)).fuse(bevel_solid).clean()
    ear = ear.intersect(prism)[0]
    skin_limits = Solid.make_box(spec.width, spec.depth, spec.height,
                                 Plane(origin=(-outer_x, 0, 0)))
    return ear.intersect(skin_limits)[0]


def build_envelope(spec: ModuleSpec = DEFAULT_SPEC,
                   dimensions: EnvelopeDimensions = EnvelopeDimensions()):
    """Make one smooth sleeve and mirror its right-hand ear across X=0."""
    sleeve = _smooth_sleeve(spec, dimensions)
    ear = _right_ear(spec, dimensions)
    return sleeve.fuse(ear, ear.mirror(Plane.YZ)).clean()
