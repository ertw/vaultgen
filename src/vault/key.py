"""Two-piece key with a keyed drive and two independently flexible catches.

Model coordinates match the measured key with the gear bottom at Z=0. Both
pieces print along +Z, splitting at the flange underside, Z=7.4. Construction
uses native geometry only; purchased meshes are never build inputs.
"""

from dataclasses import dataclass
from math import isfinite

from build123d import Compound, Edge, Face, Solid, Wire


@dataclass(frozen=True)
class KeySpec:
    @property
    def slug(self):
        return "snap_key"

    @property
    def name(self):
        return "Snap-fit Key"


@dataclass(frozen=True)
class KeyDimensions:
    # Clearance is per side. The latch projection remains larger than it.
    clearance: float = .20
    split_z: float = 7.4
    drive_width: float = 8.
    drive_depth: float = 6.
    drive_height: float = 5.
    registration_clip: float = 1.2
    beam_inner_x: float = 5.2
    beam_thickness: float = 1.2
    beam_width: float = 4.
    beam_height: float = 13.6
    root_radius: float = .6
    hook_projection: float = .6
    hook_shoulder_height: float = 12.
    hook_land: float = .4
    axial_clearance: float = .15

    def __post_init__(self):
        for name, value in vars(self).items():
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not .10 <= self.clearance <= .30:
            raise ValueError("clearance must be between 0.10 and 0.30 mm per side")
        if self.split_z != 7.4:
            raise ValueError("split_z must stay at the measured flange underside, 7.4 mm")
        if self.drive_width / 2 + self.clearance >= self.beam_inner_x - self.hook_projection:
            raise ValueError("The drive boss must leave room for the catches to flex inward")
        if self.beam_width / 2 + self.clearance >= self.drive_depth / 2:
            raise ValueError("The socket must retain torque-bearing flats on both Y sides")
        if self.beam_thickness < 1.0 or self.beam_width < 3.0:
            raise ValueError("Snap beams must retain at least 1 mm thickness and 3 mm width")
        if self.hook_projection <= self.clearance:
            raise ValueError("Hooks must project beyond the mating clearance")
        if self.hook_shoulder_height + self.hook_land >= self.beam_height:
            raise ValueError("The hook needs a tapered insertion lead above its land")
        if self.drive_height + self.drive_depth / 2 + self.clearance >= self.hook_shoulder_height:
            raise ValueError("The drive socket roof must end below the catch windows")
        if self.registration_clip <= 2 * self.clearance:
            raise ValueError("Registration corner must remain larger than the clearance")
        if self.root_radius >= self.beam_inner_x - self.drive_width / 2:
            raise ValueError("Root fillet must fit between the drive and snap beams")


def _one(shape):
    solids = shape.solids()
    if len(solids) != 1 or not shape.is_valid or len(shape.shells()) != 1:
        raise ValueError("Each key piece must be one valid solid with one boundary shell")
    return solids[0]


def _face(points):
    return Face(Wire.make_polygon(points, close=True))


def _prism(points, vector):
    return Solid.extrude(_face(points), vector)


def _drive_profile(d, clearance=0.):
    w, h = d.drive_width / 2, d.drive_depth / 2
    face = _face([(-w, -h, 0), (w-d.registration_clip, -h, 0),
                  (w, -h+d.registration_clip, 0), (w, h, 0), (-w, h, 0)])
    if clearance:
        # Intersection join retains the clipped corner as a straight plane.
        from build123d import Kind
        face = Face(face.outer_wire().offset_2d(clearance, kind=Kind.INTERSECTION))
    return face


def _beam(d):
    """One +X catch: rounded root, 45-degree lower ramp, longer upper lead."""
    x = d.beam_inner_x
    outer = x + d.beam_thickness
    z = d.split_z
    shoulder = z + d.hook_shoulder_height
    y = -d.beam_width / 2
    r = d.root_radius
    def p(a, b):
        return (a, y, b)
    points = [p(x-r, z-.2), p(outer, z-.2),
              p(outer, shoulder-d.hook_projection),
              p(outer+d.hook_projection, shoulder),
              p(outer+d.hook_projection, shoulder+d.hook_land),
              p(outer, z+d.beam_height), p(x, z+d.beam_height), p(x, z+r)]
    edges = [Edge.make_line(a,b) for a,b in zip(points, points[1:])]
    # Concave quarter-circle at the loaded root, tangent to gear and beam.
    edges.append(Edge.make_three_point_arc(p(x, z+r),
                 p(x-r+r*2**-.5, z+r-r*2**-.5), p(x-r, z)))
    edges.append(Edge.make_line(p(x-r, z), points[0]))
    return Solid.extrude(Face(Wire(edges)), (0, d.beam_width, 0))


def _gabled_void(xmin, xmax, half_y, bottom, eaves):
    """A pocket/tunnel whose ceiling closes at 45 degrees without a bridge."""
    return _prism([(xmin,-half_y,bottom), (xmin,half_y,bottom),
                   (xmin,half_y,eaves), (xmin,0,eaves+half_y),
                   (xmin,-half_y,eaves)], (xmax-xmin,0,0))


def _joint(d):
    """Return male joint, socket cutter, and hook-window floor height."""
    from build123d import Plane
    z, c = d.split_z, d.clearance
    drive = Solid.extrude(_drive_profile(d), (0,0,d.drive_height)).translate((0,0,z-.02))
    right = _beam(d)
    left = right.mirror(Plane.YZ)
    # Keep separate male solids until they are fused into the gear.
    male = (drive, right, left)

    profile = _drive_profile(d, c)
    drive_top = z + d.drive_height + c
    # Intersect the keyed outline with a gable: preserve its registration
    # flats while closing the blind drive pocket by 45-degree slopes.
    tall_drive = Solid.extrude(profile, (0,0,d.drive_height+d.drive_depth+2*c)).translate((0,0,z-.2))
    drive_roof = _gabled_void(-d.drive_width, d.drive_width,
                             d.drive_depth/2+c, z-.2, drive_top)
    socket = _one(tall_drive.intersect(drive_roof)[0])

    outer = d.beam_inner_x + d.beam_thickness + c
    half_y = d.beam_width/2 + c
    top = z + d.beam_height + c
    # Joining the lower channels removes fragile internal ribs, while
    # preserving the wider drive flats and the asymmetric corner.
    socket = socket.fuse(_gabled_void(-outer, outer, half_y, z-.2, drive_top))
    inner = d.beam_inner_x - d.hook_projection - c
    channel = _gabled_void(inner, outer, half_y, z-.2, top)
    socket = socket.fuse(channel, channel.mirror(Plane.YZ))

    # At x=outer the lower 45-degree hook ramp is this high. Axial play is
    # measured at the actual wall, not at the hook's outermost tip.
    floor = z + d.hook_shoulder_height - d.hook_projection + c - d.axial_clearance
    window = _gabled_void(outer-.01, 25., half_y, floor, top)
    socket = socket.fuse(window, window.mirror(Plane.YZ))
    return male, socket, floor


def build_key_assembly(dimensions=None):
    from .key_geometry import build_gear_blank, build_handle_blank
    d = dimensions or KeyDimensions()
    male, socket, _ = _joint(d)
    gear = _one(build_gear_blank().fuse(*male))
    handle = _one(build_handle_blank().cut(socket))
    gear.label, handle.label = 'gear', 'handle'
    return Compound(label=KeySpec().name, children=[gear, handle])


def build_key_parts(dimensions=None):
    """Two solids, each independently resting on Z=0 in print orientation."""
    assembly = build_key_assembly(dimensions)
    parts = {}
    for child in assembly.children:
        printable = child.translate((0,0,-child.bounding_box().min.Z))
        printable.parent = None
        parts[child.label] = printable
    return parts
