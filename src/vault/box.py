"""Native S4 drawer tray in module coordinates; source meshes are not build inputs.

Measured nominal dimensions from S4 Box 1F.stl. The front seating plane is
Y=188.1 and screw axes coincide with the S1F facade. Small source blends and
attachment recesses are simplified; branding is omitted. Sacrificial sheets support
both runner channels during bottom-down printing. The rear wall is solid.
"""
from dataclasses import dataclass
from math import isfinite, sqrt
from build123d import Axis, Edge, Solid, Wire, Face, Plane
from .shell import _rounded_rect


@dataclass(frozen=True)
class BoxSpec:
    family: str = 'S'
    depth_units: int = 4
    height_units: int = 1

    @property
    def name(self): return 'S4 Box 1F'

    @property
    def slug(self): return 's4_box_1f'


SPEC = BoxSpec()


def block(x0, y0, z0, x1, y1, z1):
    return Solid.make_box(x1-x0, y1-y0, z1-z0, Plane(origin=(x0,y0,z0)))


def profile(points, y, length):
    return Solid.extrude(Face(Wire.make_polygon([(x,y,z) for x,z in points], close=True)), (0,length,0))


def _runner_support(sign, clearance=0):
    """Half-mm removable sheet with repeated teeth into both channel lips.

    The source has roughly 0.7 mm teeth at irregular 8–10.7 mm intervals.
    Regular spacing keeps the first sheet layers bridging less than 9 mm,
    rather than the full channel length. Dimensions use the construction datum.
    """
    x0, x1 = sorted((sign*65.9, sign*66.4))
    y0, y1 = 28.7, 183.95
    sheet = block(x0, y0, 20.105, x1, y1, 29.483)
    tooth_width, tooth_count = .7, 18
    pitch = (y1-y0-tooth_width)/(tooth_count-1)
    teeth = [block(x0, y0+i*pitch, 18.9-clearance,
                   x1, y0+i*pitch+tooth_width, 30.1+clearance)
             for i in range(tooth_count)]
    return sheet.fuse(*teeth)


def _round_gear_channel(passage, radius):
    """Round the four long slot corners to ease bottom-up roof bridging.

    Round the cutter before adding the raised flange clearance: the latter
    interrupts the roof and must keep its measured retaining profile.
    """
    if radius == 0:
        return passage
    minimum_length = passage.bounding_box().size.X / 2
    edges = [edge for edge in passage.edges()
             if edge.bounding_box().size.X > minimum_length
             and edge.bounding_box().size.Y < 1e-6
             and edge.bounding_box().size.Z < 1e-6]
    if len(edges) != 4:
        raise ValueError('Expected four longitudinal gear-channel corners')
    return passage.fillet(radius, edges)


def _linear_gear_exit(lower=False, corner_radius=0.8):
    """Handed gear passage with a one-mm roll out through the outside wall.

    Source sections place the exits at +X/upper and -X/lower, not at both
    ends of every attachment recess. Coordinates here precede registration.
    The upper passage also has the source's rounded clearance in its roof.
    """
    y = 180.5
    floor, ceiling = 36.193, 41.393
    radius = 1.0
    inner, tangent, outside = 22.877, 66.1, 68.0
    outer = tangent + radius
    diagonal = radius / sqrt(2)
    point = lambda x, z: (x, y, z)
    edges = [
        Edge.make_line(point(inner, floor), point(tangent, floor)),
        Edge.make_three_point_arc(point(tangent, floor),
                                  point(tangent+diagonal, floor-radius+diagonal),
                                  point(outer, floor-radius)),
        Edge.make_line(point(outer, floor-radius), point(outside, floor-radius)),
        Edge.make_line(point(outside, floor-radius), point(outside, ceiling+radius)),
        Edge.make_line(point(outside, ceiling+radius), point(outer, ceiling+radius)),
        Edge.make_three_point_arc(point(outer, ceiling+radius),
                                  point(tangent+diagonal, ceiling+radius-diagonal),
                                  point(tangent, ceiling)),
        Edge.make_line(point(tangent, ceiling), point(inner, ceiling)),
        Edge.make_line(point(inner, ceiling), point(inner, floor)),
    ]
    passage = Solid.extrude(Face(Wire(edges)), (0, 4.4, 0))
    passage = _round_gear_channel(passage, corner_radius)
    if lower:
        return passage.rotate(Axis((0, 0, 24.5), (0, 1, 0)), 180)

    # The raised roof is 2.8 mm wide with R1 upper corners. Keeping the
    # surrounding shoulders leaves the front rim and a 0.591 mm top skin.
    point = lambda y, z: (inner, y, z)
    back, front, shoulder = 181.3, 184.1, 41.909
    edges = [
        Edge.make_line(point(back, ceiling), point(front, ceiling)),
        Edge.make_line(point(front, ceiling), point(front, shoulder)),
        Edge.make_three_point_arc(point(front, shoulder),
                                  point(front-radius+diagonal, shoulder+diagonal),
                                  point(front-radius, shoulder+radius)),
        Edge.make_line(point(front-radius, shoulder+radius),
                       point(back+radius, shoulder+radius)),
        Edge.make_three_point_arc(point(back+radius, shoulder+radius),
                                  point(back+radius-diagonal, shoulder+diagonal),
                                  point(back, shoulder)),
        Edge.make_line(point(back, shoulder), point(back, ceiling)),
    ]
    roof = Solid.extrude(Face(Wire(edges)), (outside-inner, 0, 0))
    return passage.fuse(roof)


def build_box(*, gear_corner_radius=0.8, runner_clearance=0.3):
    if not isfinite(gear_corner_radius) or not 0 <= gear_corner_radius <= 1.0:
        raise ValueError('gear_corner_radius must be between 0 and 1 mm')
    if not isfinite(runner_clearance) or not 0 <= runner_clearance <= 0.5:
        raise ValueError('runner_clearance must be between 0 and 0.5 mm per flank')
    # Construct at the measurement datum, then register to the sleeve/facade.
    outside = _rounded_rect(-67.1,0,67.1,185.8,3.5,lambda x,y:(x,y,6))
    part = Solid.extrude(outside,(0,0,37.5))
    # Only the rear corners are rounded in plan. The original front corners
    # are square: rounding them cuts into the closed attachment pockets and
    # creates unintended side openings near Y=187.2 after registration.
    part = part.fuse(block(-67.1,182.3,6,67.1,185.8,43.5)).clean()
    # Rounding the cavity cutter leaves a reinforcing inside floor fillet.
    floor_thickness, floor_radius = 0.8, 1.0
    floor_z = 6 + floor_thickness
    # Leave 1.3 mm behind the runner channels for two extrusion lines
    # with a 0.6 mm nozzle. Keep front/rear planes and exterior fixed.
    cavity_half_width = 64.9 - 1.3
    cavity = _rounded_rect(-cavity_half_width,3,cavity_half_width,179.2,3.5,
                           lambda x,y:(x,y,floor_z))
    cutter = Solid.extrude(cavity,(0,0,40))
    bottom_rim = [edge for edge in cutter.edges()
                  if abs(edge.bounding_box().min.Z-floor_z) < 1e-6
                  and abs(edge.bounding_box().max.Z-floor_z) < 1e-6]
    cutter = cutter.fillet(floor_radius, bottom_rim)
    part = part.cut(cutter)
    part = part.cut(block(-22.877,178.9,5,22.877,187,45))
    # Original lock opening: underside edge Y177.1, rising at 45 degrees
    # to Y178.1 at Z6 in registered coordinates. The thinner floor ends
    # within that bevel, keeping the original lock's rotation envelope clear.
    lock_profile = [(173.8,5),(174.8,6),(175.8,7),(175.8,45),
                    (187,45),(187,5)]
    lock_cut = Face(Wire.make_polygon(
        [(-22.877,y,z) for y,z in lock_profile], close=True))
    part = part.cut(Solid.extrude(lock_cut, (45.754,0,0)))
    # Chamfered outside edges and opposed runner channels, with removable
    # outer sheets carried by small teeth along the lower and upper lips.
    for sign in (-1,1):
        for pts in [[(65.1,6),(67.2,6),(67.2,8.1)],
                    [(65.1,43.5),(67.2,41.4),(67.2,43.6)]]:
            part = part.cut(profile([(sign*x,z) for x,z in pts],-1,188))
        channel=[(64.9,18.254),(66.2,19.32),(67.3,18.7),
                 (67.3,30.3),(66.2,29.68),(64.9,30.746)]
        channel = [(x,z + (-runner_clearance if z < 24.5 else runner_clearance))
                   for x,z in channel]
        part = part.cut(profile([(sign*x,z) for x,z in channel],25.8,161))
        part=part.fuse(_runner_support(sign, runner_clearance))
        # Closed attachment ends alternate with the external gear exits.
        # The central land between these passages carries the facade screw.
        a,b=sorted((sign*22.877,sign*66.3))
        z0,z1 = (7.61,12.89) if sign == 1 else (36.11,42.86)
        closed_pocket = block(a,180.5,z0,b,184.9,z1)
        closed_pocket = _round_gear_channel(closed_pocket, gear_corner_radius)
        if sign == -1:
            # Keep a wall under the outside top chamfer (|X|+Z=108.6).
            # The taller closed pocket otherwise breaks through near its roof.
            # A parallel relief retains 1 mm in X/Z (~0.71 mm normal)
            # without shortening the lower, full-width gear passage.
            relief = [(64.1,43.5),(67.4,40.2),(67.4,44),(64.1,44)]
            closed_pocket = closed_pocket.cut(
                profile([(-x,z) for x,z in relief],180,6))
        part=part.cut(closed_pocket)
        x=sign*51.45
        part=part.cut(Solid.make_cylinder(1.8,12,Plane(origin=(x,175,24.5),z_dir=(0,1,0))))
    part=part.cut(_linear_gear_exit(corner_radius=gear_corner_radius),
                  _linear_gear_exit(lower=True, corner_radius=gear_corner_radius))
    part=part.translate((0,2.3,-1))
    part.label=SPEC.name + ' — unbranded'
    if not part.is_valid or len(part.solids()) != 1 or len(part.shells()) != 1:
        raise ValueError('Expected one valid box solid with one boundary shell')
    return part


def print_orientation(part):
    """Print the tray flat on its closed bottom."""
    return part.translate((0,0,-part.bounding_box().min.Z))
