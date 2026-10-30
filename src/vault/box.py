"""Parametric drawer trays in module coordinates; meshes are not build inputs.

Measured nominal dimensions from S4 Box 1F.stl. The front seating plane is
Y=188.1 and screw axes coincide with the S1F facade. Small source blends and
attachment recesses are simplified; branding is omitted. Sacrificial sheets support
both runner channels during bottom-down printing. The shared wall setting
targets one or two perimeters in the backing and plain or Miura rear panel;
legacy native specs retain their historical independent rear-wall options.
"""
from dataclasses import dataclass
from math import ceil, isfinite, sqrt
from build123d import Axis, Edge, Solid, Wire, Face, Plane
from .shell import _rounded_rect
from .spec import (DEFAULT_SPEC, WALL_PATTERNS, validate_wall_settings,
                   wall_parameters, wall_setting_suffix, wall_target_thickness)
from .drawer import DrawerLayout, drawer_spec


@dataclass(frozen=True)
class BoxSpec:
    family: str = 'S'
    depth_units: int = 4
    height_units: int = 1
    box_floor: float = 0.8
    box_variant: str = 'plain'
    box_rear_pattern: str = 'plain'
    wall_perimeters: int | str | None = None
    nozzle_size: float = 0.6
    wall_pattern: str = 'plain'
    pattern_pitch: float = 14.0
    pattern_depth: float = 1.7

    def __post_init__(self):
        validate_wall_settings(self)
        if self.wall_perimeters is not None:
            object.__setattr__(self, 'box_rear_pattern', self.wall_pattern)
        else:
            for key, value in (('wall_pattern', 'plain'), ('pattern_pitch', 14.), ('pattern_depth', 1.7)):
                object.__setattr__(self, key, value)
        drawer_spec(self)
        if type(self.box_floor) not in (int, float) or self.box_floor not in (0.0, 0.8, 3.0):
            raise ValueError('Box floor must be 0 (floorless Gridfinity), 0.8, or 3.0 mm')
        if self.box_variant not in ('plain', 'gridfinity'):
            raise ValueError('Box variant must be plain or gridfinity')
        if self.box_floor == 0 and self.box_variant != 'gridfinity':
            raise ValueError('Floorless boxes require the Gridfinity base')
        if not isinstance(self.box_rear_pattern, str) or self.box_rear_pattern not in WALL_PATTERNS:
            raise ValueError('Box rear pattern must be plain, waffle, or miura')

    @property
    def name(self):
        floor = ' · Floorless' if self.box_floor == 0 else ' · 3 mm floor' if self.box_floor == 3 else ''
        base = ' · Gridfinity' if self.box_variant == 'gridfinity' else ''
        rear = f' · {WALL_PATTERNS[self.box_rear_pattern]} corrugated rear' if self.box_rear_pattern != 'plain' else ''
        if self.wall_perimeters is not None:
            rear += (' · Full width' if self.wall_perimeters == 'full' else
                     f' · {self.wall_perimeters} perimeter{ "s" if self.wall_perimeters == 2 else ""}, {self.nozzle_size:g} mm nozzle')
        return f'{self.family}{self.depth_units} Box {self.height_units}F' + floor + base + rear

    @property
    def slug(self):
        floor = '_floorless' if self.box_floor == 0 else '_floor_3mm' if self.box_floor == 3 else ''
        base = '_gridfinity' if self.box_variant == 'gridfinity' else ''
        rear = f'_rear_{self.box_rear_pattern}_corrugated' if self.box_rear_pattern != 'plain' else ''
        if self.wall_perimeters is not None:
            rear = wall_setting_suffix(self)
        return f'{self.family.lower()}{self.depth_units}_box_{self.height_units}f' + floor + base + rear


SPEC = BoxSpec()


def block(x0, y0, z0, x1, y1, z1):
    return Solid.make_box(x1-x0, y1-y0, z1-z0, Plane(origin=(x0,y0,z0)))


def profile(points, y, length):
    return Solid.extrude(Face(Wire.make_polygon([(x,y,z) for x,z in points], close=True)), (0,length,0))


def _runner_support(sign, clearance=0, *, layout=None, tier=0):
    """Half-mm removable sheet with repeated teeth into both channel lips.

    The source has roughly 0.7 mm teeth at irregular 8–10.7 mm intervals.
    Regular spacing keeps the first sheet layers bridging at most 6.8 mm,
    rather than the full channel length. Dimensions use the construction datum.
    """
    layout = layout or DrawerLayout()
    dx, dy = layout.width_delta, layout.depth_delta
    x0, x1 = sorted((sign*(65.9+dx), sign*(66.4+dx)))
    y0, y1 = 28.7, 183.95+dy
    sheet = block(x0, y0, 20.105, x1, y1, 29.483)
    tooth_width = .7
    tooth_count = ceil((y1-y0-tooth_width) / 7.5) + 1
    pitch = (y1-y0-tooth_width)/(tooth_count-1)
    teeth = [block(x0, y0+i*pitch, 18.9-clearance,
                   x1, y0+i*pitch+tooth_width, 30.1+clearance)
             for i in range(tooth_count)]
    return sheet.fuse(*teeth).translate((0, 0, tier))


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


def _gear_roof_clearance(x0, x1, ceiling, *, layout):
    """Raised 2.8 mm roof with R1 corners and a 0.8 mm bridging crown.

    Reuse the upper rail's flange relief above both lower rail passages to
    give drooping bridge strands 1.516 mm of headroom at the center. These
    coordinates precede box registration; the relief always rises in Z.
    """
    radius = 1.0
    diagonal = radius / sqrt(2)
    point = lambda y, z: (x0, y, z)
    back, front = 181.3+layout.depth_delta, 184.1+layout.depth_delta
    shoulder = ceiling + .516
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
    return Solid.extrude(Face(Wire(edges)), (x1-x0, 0, 0))


def _linear_gear_exit(lower=False, corner_radius=0.8, *, layout=None):
    """Handed gear passage with a one-mm roll out through the outside wall.

    Source sections place the exits at +X/upper and -X/lower, not at both
    ends of every attachment recess. Coordinates here precede registration.
    Both roofs have the upper source passage's rounded clearance profile.
    """
    layout = layout or DrawerLayout()
    dx, dy = layout.width_delta, layout.depth_delta
    y = 180.5 + dy
    floor, ceiling = 36.193, 41.393
    radius = 1.0
    inner, tangent, outside = 22.877, 66.1+dx, 68.0+dx
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
        passage = passage.rotate(Axis((0, 0, 24.5), (0, 1, 0)), 180)
        # Rotate the handed slot first so the added arch stays above the rail.
        return passage.fuse(_gear_roof_clearance(
            -outside, -inner, 49-floor, layout=layout))

    # Original upper shoulders retain the front rim and 0.591 mm top skin.
    return passage.fuse(_gear_roof_clearance(inner, outside, ceiling, layout=layout))


def build_box(*, spec=DEFAULT_SPEC, gear_corner_radius=0.8, runner_clearance=0.3,
              include_supports=True):
    """Build the tray, optionally omitting its removable runner-channel sheets.

    Printable builds keep the default supports. The assembled scene uses
    ``include_supports=False`` so slides occupy the finished channels.
    """
    floor_thickness = getattr(spec, 'box_floor', 0.8)
    box_variant = getattr(spec, 'box_variant', 'plain')
    box_rear_pattern = getattr(spec, 'box_rear_pattern', 'plain')
    wall_settings = wall_parameters(spec) if hasattr(spec, 'wall_perimeters') else {}
    layout = DrawerLayout(spec)
    spec = layout.spec
    box_spec = BoxSpec(spec.family, spec.depth_units, spec.height_units,
                       floor_thickness, box_variant, box_rear_pattern, **wall_settings)
    dx, dy, dz = layout.width_delta, layout.depth_delta, layout.height_delta
    if not isfinite(gear_corner_radius) or not 0 <= gear_corner_radius <= 1.0:
        raise ValueError('gear_corner_radius must be between 0 and 1 mm')
    if not isfinite(runner_clearance) or not 0 <= runner_clearance <= 0.5:
        raise ValueError('runner_clearance must be between 0 and 0.5 mm per flank')
    # Construct at the measurement datum, then register to the sleeve/facade.
    outside = _rounded_rect(-67.1-dx,0,67.1+dx,185.8+dy,3.5,lambda x,y:(x,y,6))
    part = Solid.extrude(outside,(0,0,37.5+dz))
    # Only the rear corners are rounded in plan. The original front corners
    # are square: rounding them cuts into the closed attachment pockets and
    # creates unintended side openings near Y=187.2 after registration.
    part = part.fuse(block(-67.1-dx,182.3+dy,6,67.1+dx,185.8+dy,43.5+dz)).clean()
    # Rounding the cavity cutter leaves a reinforcing inside floor fillet.
    floor_radius = 1.0
    # Floorless Gridfinity retains the thin foundation beneath its webs and
    # perimeter; socket openings are cut through it after the grid is fused.
    floor_z = 6 + max(0.8, floor_thickness)
    # Change the cavity side of the backing to target the selected perimeters.
    # The runner's external profile stays fixed. Legacy/full retains 1.3 mm.
    backing = (wall_target_thickness(box_spec)
               if box_spec.wall_perimeters in (1, 2) else 1.3)
    cavity_half_width = 64.9 + dx - backing
    cavity = _rounded_rect(-cavity_half_width,3,cavity_half_width,179.2+dy,3.5,
                           lambda x,y:(x,y,floor_z))
    cutter = Solid.extrude(cavity,(0,0,40+dz))
    bottom_rim = [edge for edge in cutter.edges()
                  if abs(edge.bounding_box().min.Z-floor_z) < 1e-6
                  and abs(edge.bounding_box().max.Z-floor_z) < 1e-6]
    cutter = cutter.fillet(floor_radius, bottom_rim)
    part = part.cut(cutter)
    part = part.cut(block(-22.877,178.9+dy,5,22.877,187+dy,45+dz))
    # Original lock opening: underside edge Y177.1, rising at 45 degrees
    # to Y178.1 at Z6 in registered coordinates. The thinner floor ends
    # within that bevel, keeping the original lock's rotation envelope clear.
    lock_profile = [(173.8,5),(174.8,6),(175.8,7),(175.8,45),
                    (187,45),(187,5)]
    lock_profile = [(y+dy, z+(dz if z == 45 else 0)) for y,z in lock_profile]
    lock_cut = Face(Wire.make_polygon(
        [(-22.877,y,z) for y,z in lock_profile], close=True))
    part = part.cut(Solid.extrude(lock_cut, (45.754,0,0)))
    # Chamfered outside edges and opposed runner channels, with removable
    # outer sheets carried by small teeth along the lower and upper lips.
    for sign in (-1,1):
        for pts in [[(65.1,6),(67.2,6),(67.2,8.1)],
                    [(65.1,43.5+dz),(67.2,41.4+dz),(67.2,43.6+dz)]]:
            part = part.cut(profile([(sign*(x+dx),z) for x,z in pts],-1,188+dy))
        channel=[(64.9,18.254),(66.2,19.32),(67.3,18.7),
                 (67.3,30.3),(66.2,29.68),(64.9,30.746)]
        channel = [(x,z + (-runner_clearance if z < 24.5 else runner_clearance))
                   for x,z in channel]
        for tier in spec.tier_offsets:
            part = part.cut(profile([(sign*(x+dx),z+tier) for x,z in channel],25.8,161+dy))
            if include_supports:
                part=part.fuse(_runner_support(sign, runner_clearance, layout=layout, tier=tier))
        # Closed attachment ends alternate with the external gear exits.
        # Their blind ends locate the rail noses in the unlocked installation
        # position. Keep the proven S stop datum for every family: M/L rails
        # extend only the outgoing tail, not the nose or central tooth train.
        # Only the opposite, open passages follow the outside wall.
        a,b=sorted((sign*22.877,sign*66.3))
        z0,z1 = (7.61,12.89) if sign == 1 else (36.11,42.86)
        closed_pocket = block(a,180.5+dy,z0,b,184.9+dy,z1)
        closed_pocket = _round_gear_channel(closed_pocket, gear_corner_radius)
        if sign == 1:
            # Relieve the blind half of the lower track as well as its exit;
            # ending at the same X datum preserves the installation stop.
            closed_pocket = closed_pocket.fuse(
                _gear_roof_clearance(a, b, z1, layout=layout))
        if sign == -1 and spec.height_units == 1:
            # Keep a wall under the outside top chamfer (|X|+Z=108.6).
            # The taller closed pocket otherwise breaks through near its roof.
            # A parallel relief retains 1 mm in X/Z (~0.71 mm normal)
            # without shortening the lower, full-width gear passage.
            relief = [(64.1,43.5),(67.4,40.2),(67.4,44),(64.1,44)]
            closed_pocket = closed_pocket.cut(
                profile([(-x-dx,z) for x,z in relief],180+dy,6))
        part=part.cut(closed_pocket)
    for x,z in layout.screw_positions:
        part=part.cut(Solid.make_cylinder(1.8,12,Plane(origin=(x,175+dy,z+1),z_dir=(0,1,0))))
    part=part.cut(_linear_gear_exit(corner_radius=gear_corner_radius, layout=layout),
                  _linear_gear_exit(lower=True, corner_radius=gear_corner_radius, layout=layout))
    part=part.translate((0,2.3,-1))
    if box_rear_pattern != 'plain' or box_spec.wall_perimeters in (1, 2):
        from .box_wall_patterns import apply_box_rear_pattern
        part = apply_box_rear_pattern(part, box_spec)
    if box_variant == 'gridfinity':
        from .gridfinity import build_gridfinity_base
        part = part.fuse(build_gridfinity_base(box_spec)).clean()
        if floor_thickness == 0:
            from .gridfinity import apply_gridfinity_floorless
            part = apply_gridfinity_floorless(part, box_spec)
    part.label=box_spec.name + ' — unbranded'
    if not part.is_valid or len(part.solids()) != 1 or len(part.shells()) != 1:
        raise ValueError('Expected one valid box solid with one boundary shell')
    return part


def print_orientation(part):
    """Print the tray flat on its closed bottom."""
    return part.translate((0,0,-part.bounding_box().min.Z))
