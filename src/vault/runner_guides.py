"""Native depth-sized runner guides for S, M and L drawers.

The supplied runner-guide files contain two copies of the same guide. Local X
is its 27 mm width, Y its travel direction, and Z=0 is the flat print bed.
Rounded channels, retaining lips and the travel slot are constructed from
editable analytic dimensions; construction never reads a reference mesh.
"""

from dataclasses import dataclass
from math import sqrt

from build123d import Edge, Face, Solid, Wire

from .shell import _rounded_rect


@dataclass(frozen=True)
class RunnerGuideSpec:
    depth_units: int = 4

    def __post_init__(self):
        if type(self.depth_units) is not int or not 3 <= self.depth_units <= 7:
            raise ValueError("Runner guides support integer depths 3 through 7")

    @property
    def slug(self):
        return f"x{self.depth_units}_runner_guides"

    @property
    def name(self):
        return f"x{self.depth_units} Runner Guides"

    @property
    def length(self):
        return 42.0 * self.depth_units + 17.5

    @property
    def slot_end(self):
        # The x3 purchased guide has one millimetre less travel than the
        # otherwise regular half-depth progression.
        return 21.0 * self.depth_units + 43.458 - (self.depth_units == 3)

    @property
    def lip_start(self):
        return self.slot_end - 6.808


SPEC = RunnerGuideSpec()
WIDTH = 27.0
HEIGHT = 9.4
CHANNEL_SIDE = 3.9898
LIP_SIDE = 6.2045
SLOT_RADIUS = 3.55
SLOT_START = 9.458


def _one(shape):
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError("Runner guide must be one valid connected solid")
        shape = shape[0]
    solids = shape.solids()
    if not shape.is_valid or len(solids) != 1:
        raise ValueError("Runner guide must be one valid connected solid")
    return solids[0]


def _capsule(y0, y1, radius, z):
    x = WIDTH / 2
    edges = [
        Edge.make_line((x-radius, y0, z), (x-radius, y1, z)),
        Edge.make_three_point_arc((x-radius, y1, z), (x, y1+radius, z),
                                  (x+radius, y1, z)),
        Edge.make_line((x+radius, y1, z), (x+radius, y0, z)),
        Edge.make_three_point_arc((x+radius, y0, z), (x, y0-radius, z),
                                  (x-radius, y0, z)),
    ]
    return Face(Wire(edges))


def _channel_profile():
    """Female T channel before rounding its 1.6 mm retaining lip's top."""
    a, b, r, c = CHANNEL_SIDE, LIP_SIDE, 1.2, sqrt(.5)
    def p(x, z):
        return (x, 0, z)
    left = [
        Edge.make_three_point_arc(p(a+r, 4.6), p(a+r-r*c, 5.8-r*c), p(a, 5.8)),
        Edge.make_line(p(a, 5.8), p(a, 6.6)),
        Edge.make_three_point_arc(p(a, 6.6), p(a+r-r*c, 6.6+r*c), p(a+r, 7.8)),
        Edge.make_line(p(a+r, 7.8), p(b, 7.8)),
        Edge.make_line(p(b, 7.8), p(b, 12)),
    ]
    right = []
    for edge in reversed(left):
        points = [edge.position_at(t) for t in (1, .5, 0)]
        points = [(WIDTH-q.X, q.Y, q.Z) for q in points]
        right.append(Edge.make_line(points[0], points[2]) if edge.geom_type.name == "LINE"
                     else Edge.make_three_point_arc(*points))
    return Face(Wire(left + [Edge.make_line(p(b, 12), p(WIDTH-b, 12))]
                     + right + [Edge.make_line(p(WIDTH-a-r, 4.6), p(a+r, 4.6))]))


def build_runner_guide(*, spec=SPEC):
    """Build one guide in the original flat printing orientation."""
    if not isinstance(spec, RunnerGuideSpec):
        raise TypeError("spec must be a RunnerGuideSpec")
    length = spec.length
    outer = Solid.extrude(_rounded_rect(0, 0, WIDTH, length, 3,
                                       lambda x, y: (x, y, 0)), (0, 0, HEIGHT))
    bottom = [e for e in outer.edges()
              if e.bounding_box().size.Z < 1e-7 and e.center().Z < 1]
    outer = _one(outer.fillet(1.2, bottom))

    # The channel runs out of the front; the back has a rounded closed end.
    channel = Solid.extrude(_rounded_rect(CHANNEL_SIDE, 13.65, WIDTH-CHANNEL_SIDE,
                                          length+10, 2, lambda x, y: (x, y, 4.6)),
                            (0, 0, 10))
    bottom = [e for e in channel.edges() if abs(e.center().Z-4.6) < 1e-7]
    channel = _one(channel.fillet(1.2, bottom))
    tee = Solid.extrude(_channel_profile(), (0, length+10, 0))
    opening = Solid.extrude(_rounded_rect(CHANNEL_SIDE, 12, WIDTH-CHANNEL_SIDE,
                                          spec.lip_start, 1, lambda x, y: (x, y, 4)),
                            (0, 0, 10))
    channel = _one(channel.intersect(_one(tee.fuse(opening))))
    shape = _one(outer.cut(channel))

    # Round the front lip corners before rolling the top edges. This ordering
    # preserves the original R2 insertion flare rather than capping the lips
    # with a sharp edge at the front of the guide.
    front_lips = [e for e in shape.edges()
                  if abs(e.center().Y-length) < 1e-5
                  and min(abs(e.center().X-LIP_SIDE),
                          abs(e.center().X-(WIDTH-LIP_SIDE))) < 1e-5
                  and e.geom_type.name == "LINE" and e.bounding_box().size.Z > 1.5]
    shape = _one(shape.fillet(2, front_lips))
    rolled_top = [e for e in shape.edges()
                  if abs(e.center().Z-HEIGHT) < 1e-5
                  and (e.center().X < 3.1 or e.center().X > WIDTH-3.1
                       or e.center().Y < 5 or e.center().Y > spec.lip_start+.01)]
    shape = _one(shape.fillet(1.2, rolled_top))

    # Chamfer the entire slot rim, including its quarter-circle transition
    # between the low channel floor and the tall closed back.
    slot = Solid.extrude(_capsule(SLOT_START, spec.slot_end, SLOT_RADIUS, -1),
                         (0, 0, HEIGHT+2))
    shape = _one(shape.cut(slot))
    slot_rim = [e for e in shape.edges()
                if e.bounding_box().min.Z > 3
                and e.bounding_box().min.X > WIDTH/2-SLOT_RADIUS-1e-5
                and e.bounding_box().max.X < WIDTH/2+SLOT_RADIUS+1e-5]
    return _one(shape.chamfer(.8, None, slot_rim))


def build_runner_guides(*, spec=SPEC):
    """Two identical guides, labeled by installation side for printing."""
    shape = build_runner_guide(spec=spec)
    return {"left": shape, "right": shape.moved(shape.location)}
