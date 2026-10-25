"""Native universal drawer slides for x3 through x7 runner depths.

The purchased pair contains two copies of the same part. The fixed rolled
male dovetail and rounded flange are reconstructed as native curves; depth
changes the straight shank and the midpoint stop, never the mating profile.
X is centered on the slide, Y follows its length, and Z=0 is the print bed.
Reference meshes are used only by the independent comparison tool.
"""
from dataclasses import dataclass
from math import sqrt

from build123d import Edge, Face, Plane, Solid, Wire


@dataclass(frozen=True)
class RunnerSlideSpec:
    depth_units: int = 4

    def __post_init__(self):
        if type(self.depth_units) is not int or not 3 <= self.depth_units <= 7:
            raise ValueError("Runner slides support integer depths 3 through 7")

    @property
    def name(self):
        return f"x{self.depth_units} Runner Slides"

    @property
    def slug(self):
        return f"x{self.depth_units}_runner_slides"

    @property
    def length(self):
        return 42 * self.depth_units - 8

    @property
    def flange_end(self):
        return 21 * self.depth_units + 9.1093


SPEC = RunnerSlideSpec()
WIDTH = 18.22
HEIGHT = 8.979
STEM_WIDTH = 14.4914
FLANGE_HEIGHT = 2.6957


def _one(shape):
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError("A runner slide must remain connected")
        shape = shape[0]
    if not shape.is_valid or len(shape.solids()) != 1:
        raise ValueError("Invalid native runner slide")
    return shape.solids()[0]


def _section(steps, length):
    """Extrude XZ profile from line/three-point arc instructions."""
    edges = []
    for step in steps:
        points = [(x - WIDTH / 2, 0, z) for x, z in step]
        edges.append(Edge.make_line(*points) if len(points) == 2
                     else Edge.make_three_point_arc(*points))
    return Solid.extrude(Face(Wire(edges)), (0, length, 0))


def _body(length):
    c = sqrt(.5)
    # The source dovetail's root and crown are small blended arcs. These
    # measured stations are fixed cross-section datums, not mesh vertices
    # loaded at construction time. The root arc replaces source faceting.
    half = [
        ((WIDTH / 2, 0), (2.8643, 0)),
        ((2.8643, 0), (2.8643-c, 1-c), (1.8643, 1)),
        ((1.8643, 1), (1.8643, 5.3)),
        ((1.8643, 5.3), (2.8643-c, 5.3+c), (2.8643, 6.3)),
        ((2.8643, 6.3), (2.8643, 6.679)),
        ((2.8643, 6.679), (2.8715, 6.732), (2.8926, 6.7811)),
        ((2.8926, 6.7811), (3.2256, 6.7811)),
        ((3.2256, 6.7811), (4.0635, 7.7036), (3.8076, 8.308)),
        ((3.8076, 8.308), (3.3184, 8.8091)),
        ((3.3184, 8.8091), (3.29, 8.8896), (3.3896, HEIGHT)),
        ((3.3896, HEIGHT), (WIDTH / 2, HEIGHT)),
    ]
    other = [tuple((WIDTH-x, z) for x, z in reversed(step))
             for step in reversed(half)]
    return _section(half + other, length)


def _flange(length, *, block=False):
    r = 1.2
    c = sqrt(.5)
    if block:
        # The short solid head is the end stop. Its upper surface meets the
        # dovetail root, while its underside shares the flange's R1.2 rounds.
        half = [((WIDTH/2, 0), (r, 0)),
                ((r, 0), (r-r*c, r-r*c), (0, r)),
                ((0, r), (0, 6.7811)),
                ((0, 6.7811), (WIDTH/2, 6.7811))]
    else:
        h = FLANGE_HEIGHT
        half = [((WIDTH/2, 0), (r, 0)),
                ((r, 0), (r-r*c, r-r*c), (0, r)),
                ((0, r), (0, h-r)),
                ((0, h-r), (r-r*c, h-r+r*c), (r, h)),
                ((r, h), (WIDTH/2, h))]
    other = [tuple((WIDTH-x, z) for x, z in reversed(step))
             for step in reversed(half)]
    return _section(half+other, length)


def _plan_mask(length, rear_radius):
    """Rounded outline clips the nose and both flange/stop ends."""
    w, r, t = WIDTH, 1.537, rear_radius
    c = sqrt(.5)
    steps = [((r, 0), (w-r, 0)),
             ((w-r, 0), (w-r+r*c, r-r*c), (w, r)),
             ((w, r), (w, length-t)),
             ((w, length-t), (w-t+t*c, length-t+t*c), (w-t, length)),
             ((w-t, length), (t, length)),
             ((t, length), (t-t*c, length-t+t*c), (0, length-t)),
             ((0, length-t), (0, r)),
             ((0, r), (r-r*c, r-r*c), (r, 0))]
    edges = []
    for step in steps:
        points = [(x-w/2, y, -1) for x, y in step]
        edges.append(Edge.make_line(*points) if len(points) == 2
                     else Edge.make_three_point_arc(*points))
    return Solid.extrude(Face(Wire(edges)), (0, 0, HEIGHT+2))


def build_runner_slide(*, spec=SPEC):
    """One printable slide, shared by all S/M/L widths and height tiers."""
    if not isinstance(spec, RunnerSlideSpec):
        raise TypeError("spec must be a RunnerSlideSpec")
    flange = _one(_flange(spec.flange_end).intersect(_plan_mask(spec.flange_end, 1.5)))
    head_length = 7.2435
    head = _one(_flange(head_length, block=True).intersect(_plan_mask(head_length, 1.2)))
    shape = _one(_body(spec.length).fuse(flange, head))
    # Preserve the supplied 0.4 mm underside relief at the flange transition.
    groove = Solid.make_cylinder(.2, WIDTH+2,
        Plane(origin=(-WIDTH/2-1, spec.flange_end+.2, 0), z_dir=(1, 0, 0)))
    shape = _one(shape.cut(groove))
    # Preserve the source nose relief below the crown chamfer.
    points = [(-WIDTH, -1, 6.879), (-WIDTH, 0, 6.879),
              (-WIDTH, .048, HEIGHT), (-WIDTH, .048, HEIGHT+1),
              (-WIDTH, -1, HEIGHT+1)]
    lead = Solid.extrude(Face(Wire.make_polygon(points, close=True)), (WIDTH*2, 0, 0))
    shape = _one(shape.cut(lead))
    # Relieve the crown at the insertion end with a 1 mm, 45 degree
    # lead-in, measured back from the original crown edge at Y=.048.
    # Use a planar cut so the small blended dovetail sides stay robust.
    crown_setback = 1.048
    points = [(-WIDTH, -1, HEIGHT-crown_setback-1),
              (-WIDTH, crown_setback+1, HEIGHT+1),
              (-WIDTH, crown_setback+1, HEIGHT+2),
              (-WIDTH, -1, HEIGHT+2)]
    chamfer = Solid.extrude(Face(Wire.make_polygon(points, close=True)),
                            (WIDTH*2, 0, 0))
    return _one(shape.cut(chamfer))


def build_runner_slides(*, spec=SPEC):
    """Return the two identical pieces in the source pair, both on the bed.

    Print one left/right pair per populated runner tier. The names indicate
    installation sides; the source pair does not have handed geometry.
    """
    return {name: build_runner_slide(spec=spec) for name in ("left", "right")}
