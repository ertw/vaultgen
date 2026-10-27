"""Parametric Vault sleeve with repeated native runner and retention features.

ModuleSpec controls box size. ShellDimensions controls fixed mating sections;
features move with the front/back/side anchors and repeat on the 48 mm tier
pitch. No source mesh or measured profile table is needed for construction.
"""
from dataclasses import dataclass
from math import sqrt, atan2, cos, sin, pi, isfinite
from build123d import Edge, Wire, Face, Solid, Plane, Axis
from .spec import ModuleSpec, DEFAULT_SPEC, TIER_PITCH
from .envelope import EnvelopeDimensions, build_envelope


@dataclass(frozen=True)
class ShellDimensions:
    """Fixed manufacturing and mating dimensions, in millimetres."""

    envelope: EnvelopeDimensions = EnvelopeDimensions()
    skin: float = 3.0
    side_wall: float = 14.761
    back_wall: float = 0.9  # Three 0.3 mm layers with the closed back on the bed.
    cavity_corner_radius: float = 1.0
    channel_inner_inset: float = 13.20997
    channel_outer_inset: float = 3.009775
    channel_floor: float = 9.501408
    channel_ceiling: float = 37.501408
    channel_back_radius: float = 3.0
    channel_mouth_radius: float = 2.0
    runner_opening_start: float = 27.9496
    runner_opening_floor: float = 13.891361
    runner_opening_ceiling: float = 33.111454
    runner_opening_radius: float = 2.0
    bore_inset: float = 8.1543
    bore_lower_z: float = 4.753513
    bore_upper_z: float = 42.252872
    bore_entry_radius: float = 2.8
    bore_radius: float = 1.8
    bore_entry_depth: float = 5.0
    bore_taper_depth: float = 1.0
    bore_depth: float = 100.0
    stopper_center_offset: float = 28.50005
    stopper_center_z: float = 23.5009
    stopper_length: float = 16.7
    stopper_height: float = 6.32
    stopper_chamfer: float = 0.96
    divider_access_width: float = 4.4
    divider_access_entry_radius: float = 3.0
    rear_notch_center_x: float = 15.13
    rear_notch_width: float = 3.5
    rear_notch_depth: float = 5.97
    rear_notch_drop: float = 2.65
    pocket_front_offset: float = 0.8
    pocket_length: float = 5.0
    # The complete relief/lip section moves with this floor datum. Its height
    # is fixed; the top of the cutter overlaps the existing runner void.
    pocket_floor: float = 6.4914
    pocket_roll: float = 1.0
    # Sacrificial ledge support for closed-back-down printing (+Y growth).
    # Set thickness to zero to inspect the finished mechanical interface.
    pocket_support_thickness: float = 0.6
    pocket_support_gap: float = 0.3
    pocket_support_tooth: float = 0.7
    catch_front_offset: float = 9.2
    catch_length: float = 3.7
    catch_depth: float = 2.0
    catch_radius: float = 18.0
    catch_return_radius: float = 10.0
    catch_exit_rise: float = 1.0

    def __post_init__(self):
        if not isfinite(self.pocket_support_thickness) or self.pocket_support_thickness < 0:
            raise ValueError('pocket_support_thickness must be finite and nonnegative')
        for name in ('pocket_support_gap', 'pocket_support_tooth'):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.pocket_support_gap >= self.pocket_length:
            raise ValueError('pocket_support_gap must be shorter than the pocket')
        if self.pocket_support_thickness >= POCKET_LEDGE_HEIGHT - .15:
            raise ValueError('pocket_support_thickness must leave clearance above the pocket floor')


POCKET_SECTION_HEIGHT = 5.2
POCKET_LEDGE_HEIGHT = 2.1564
POCKET_HOOK_TOP = 5.2186
DEFAULT_DIMENSIONS = ShellDimensions()


def _face(points, mapping):
    """Planar polygon; mapping converts its 2D coordinates to XYZ."""
    return Face(Wire.make_polygon([mapping(*p) for p in points], close=True))


def _rounded_rect(x0, y0, x1, y1, radius, mapping):
    """A precise planar rounded rectangle built from lines and circular arcs."""
    corner_factor = 1 - sqrt(0.5)
    corners = [
        (x0 + radius, y0),
        (x1 - radius, y0),
        (x1, y0 + radius),
        (x1, y1 - radius),
        (x1 - radius, y1),
        (x0 + radius, y1),
        (x0, y1 - radius),
        (x0, y0 + radius)
    ]
    arc_midpoints = [
        (x1 - radius * corner_factor, y0 + radius * corner_factor),
        (x1 - radius * corner_factor, y1 - radius * corner_factor),
        (x0 + radius * corner_factor, y1 - radius * corner_factor),
        (x0 + radius * corner_factor, y0 + radius * corner_factor)
    ]
    edges = []
    for i in range(4):
        edges.append(
            Edge.make_line(mapping(*corners[2 * i]), mapping(*corners[2 * i + 1]))
        )
        edges.append(
            Edge.make_three_point_arc(
                mapping(*corners[2 * i + 1]),
                mapping(*arc_midpoints[i]),
                mapping(*corners[(2 * i + 2) % 8])
            )
        )
    return Face(Wire(edges))


def _runner_profile(start, floor, ceiling, back_radius, end, mouth_radius, mapping):
    """Runner void: rounded closed back and outward flared mouth."""
    corner_factor = sqrt(0.5)
    back_lower = (start, floor + back_radius)
    floor_start = (start + back_radius, floor)
    floor_end = (end - mouth_radius, floor)
    mouth_lower = (end, floor - mouth_radius)
    outer_lower = (end + 1, floor - mouth_radius)
    outer_upper = (end + 1, ceiling + mouth_radius)
    mouth_upper = (end, ceiling + mouth_radius)
    ceiling_end = (end - mouth_radius, ceiling)
    ceiling_start = (start + back_radius, ceiling)
    back_upper = (start, ceiling - back_radius)

    def line(p, q):
        return Edge.make_line(mapping(*p), mapping(*q))

    def arc(p, q, r):
        return Edge.make_three_point_arc(mapping(*p), mapping(*q), mapping(*r))

    edges = [
        arc(
            back_lower,
            (
                start + back_radius - back_radius * corner_factor,
                floor + back_radius - back_radius * corner_factor
            ),
            floor_start
        ),
        line(floor_start, floor_end),
        arc(
            floor_end,
            (
                end - mouth_radius + mouth_radius * corner_factor,
                floor - mouth_radius + mouth_radius * corner_factor
            ),
            mouth_lower
        ),
        line(mouth_lower, outer_lower),
        line(outer_lower, outer_upper),
        line(outer_upper, mouth_upper),
        arc(
            mouth_upper,
            (
                end - mouth_radius + mouth_radius * corner_factor,
                ceiling + mouth_radius - mouth_radius * corner_factor
            ),
            ceiling_end
        ),
        line(ceiling_end, ceiling_start),
        arc(
            ceiling_start,
            (
                start + back_radius - back_radius * corner_factor,
                ceiling - back_radius + back_radius * corner_factor
            ),
            back_upper
        ),
        line(back_upper, back_lower)
    ]
    return Face(Wire(edges))


def _slot_wire(x, center_y, center_z, dimensions, extra=0):
    radius = dimensions.stopper_height / 2 + extra
    half_straight = (dimensions.stopper_length - dimensions.stopper_height) / 2
    start, end = center_y - half_straight, center_y + half_straight
    point = lambda y, z: (x, y, z)
    return Wire([
        Edge.make_line(point(start, center_z-radius), point(end, center_z-radius)),
        Edge.make_three_point_arc(point(end, center_z-radius),
                                  point(end+radius, center_z),
                                  point(end, center_z+radius)),
        Edge.make_line(point(end, center_z+radius), point(start, center_z+radius)),
        Edge.make_three_point_arc(point(start, center_z+radius),
                                  point(start-radius, center_z),
                                  point(start, center_z-radius)),
    ])


def _rear_notches(spec, dimensions, bank_x):
    """Mirrored entry reliefs on the rear edge of the top skin."""
    cutters = []
    for side in (-1, 1):
        x = bank_x + side * dimensions.rear_notch_center_x - dimensions.rear_notch_width / 2
        point = lambda y, drop: (
            x, y * dimensions.rear_notch_depth / 5.97,
            spec.height + drop * dimensions.rear_notch_drop / 2.65,
        )
        entry = point(0, -2.65)
        ramp_start = point(1.6444, -.6821)
        ramp_end = point(3.4835, -.3497)
        exit_point = point(5.97, 0)
        edges = [
            Edge.make_three_point_arc(entry, point(.4565, -1.3784), ramp_start),
            Edge.make_line(ramp_start, ramp_end),
            Edge.make_three_point_arc(ramp_end, point(4.7195, -.1299), exit_point),
            Edge.make_line(exit_point, point(5.97, 1)),
            Edge.make_line(point(5.97, 1), point(-.1, 1)),
            Edge.make_line(point(-.1, 1), point(-.1, -2.65)),
            Edge.make_line(point(-.1, -2.65), entry),
        ]
        cutters.append(Solid.extrude(Face(Wire(edges)), (dimensions.rear_notch_width, 0, 0)))
    return cutters


def _central_recesses(spec, dimensions, bank_x):
    """R18 catch bowl with tangent R10 returns and a shallow circular exit."""
    floor, depth = dimensions.skin, dimensions.catch_depth
    radius, blend = dimensions.catch_radius, dimensions.catch_return_radius
    width = sqrt((radius + blend)**2 - (radius + blend - depth)**2)
    junction_x = radius / (radius + blend) * width
    junction_z = floor - depth + radius - radius / (radius + blend) * (radius + blend - depth)
    blend_center_z = floor - blend
    angle = (atan2(junction_z - blend_center_z, junction_x - width) + pi / 2) / 2
    blend_mid = (width + blend * cos(angle), blend_center_z + blend * sin(angle))
    back = spec.depth - dimensions.catch_front_offset
    parts = []
    for upper in (False, True):
        height = lambda z: spec.height - z if upper else z
        point = lambda x, z: (bank_x + x, back, height(z))
        edges = [
            Edge.make_three_point_arc(
                point(-width, floor), point(-blend_mid[0], blend_mid[1]),
                point(-junction_x, junction_z)),
            Edge.make_three_point_arc(
                point(-junction_x, junction_z), point(0, floor-depth),
                point(junction_x, junction_z)),
            Edge.make_three_point_arc(point(junction_x, junction_z), point(*blend_mid), point(width, floor)),
            Edge.make_line(point(width, floor), point(width, floor+1)),
            Edge.make_line(point(width, floor+1), point(-width, floor+1)),
            Edge.make_line(point(-width, floor+1), point(-width, floor)),
        ]
        parts.append(Solid.extrude(Face(Wire(edges)), (0, dimensions.catch_length, 0)))
        point = lambda x, z: (bank_x + x, back + dimensions.catch_length, height(z))
        rise = dimensions.catch_exit_rise
        edges = [
            Edge.make_three_point_arc(point(-width, floor), point(0, floor-rise), point(width, floor)),
            Edge.make_line(point(width, floor), point(width, floor+1.1)),
            Edge.make_line(point(width, floor+1.1), point(-width, floor+1.1)),
            Edge.make_line(point(-width, floor+1.1), point(-width, floor)),
        ]
        parts.append(Solid.extrude(Face(Wire(edges)), (0, rise, -rise if upper else rise)))
    return parts


def _pocket_wire(x, lower_radius, spec, dimensions):
    """Rounded YZ pocket with an independent lower and upper roll."""
    lower, upper = lower_radius, dimensions.pocket_roll
    end = spec.depth - dimensions.pocket_front_offset
    start = end - dimensions.pocket_length
    floor = dimensions.pocket_floor
    ceiling = floor + POCKET_SECTION_HEIGHT
    factor = 1 - sqrt(.5)
    points = [(start+lower, floor), (end-lower, floor), (end, floor+lower),
              (end, ceiling-upper), (end-upper, ceiling), (start+upper, ceiling),
              (start, ceiling-upper), (start, floor+lower)]
    middle = [(end-lower*factor, floor+lower*factor), (end-upper*factor, ceiling-upper*factor),
              (start+upper*factor, ceiling-upper*factor), (start+lower*factor, floor+lower*factor)]
    point = lambda yz: (x, *yz)
    edges = []
    for index in range(4):
        edges.append(Edge.make_line(point(points[2*index]), point(points[2*index+1])))
        edges.append(Edge.make_three_point_arc(
            point(points[2*index+1]), point(middle[index]),
            point(points[(2*index+2)%8])))
    return Wire(edges)


def _mouth_hook(spec, dimensions):
    """Mating outline measured from the outside wall and pocket floor."""
    back = spec.depth - dimensions.pocket_front_offset - dimensions.pocket_length - .01
    point = lambda inset, rise: (
        spec.half_width - inset, back, dimensions.pocket_floor + rise - .002)
    outline = [(15.5004, 0), (7.3740, 0), (6.6669, 1.7071),
               (7.1162, POCKET_LEDGE_HEIGHT), (6.7626, 3.01),
               (dimensions.channel_outer_inset, 3.01),
               (dimensions.channel_outer_inset, POCKET_HOOK_TOP),
               (15.5004, POCKET_HOOK_TOP)]
    edges = [
        Edge.make_line(point(*outline[0]), point(*outline[1])),
        Edge.make_three_point_arc(point(*outline[1]), point(6.4501, .6173), point(*outline[2])),
        Edge.make_line(point(*outline[2]), point(*outline[3])),
        Edge.make_three_point_arc(point(*outline[3]), point(7.2245, 2.7014), point(*outline[4])),
    ]
    edges += [Edge.make_line(point(*outline[index]), point(*outline[(index+1)%8])) for index in range(4, 8)]
    return Solid.extrude(Face(Wire(edges)), (0, spec.depth + .1 - back, 0))


def _place_mouth_feature(part, upper, tier_z):
    """Place the lower mate at -X and the upper mate at +X.

    The source STL's height/travel permutation reflected X. The assembled
    interface requires a proper rotation, so exchange the two pocket sides.
    """
    if upper:
        part = part.rotate(Axis((0, 0, (TIER_PITCH - 1) / 2), (0, 1, 0)), 180)
    return part.mirror(Plane.YZ).translate((0, 0, tier_z))


def _mouth_pockets(spec, dimensions, tier_z):
    """Opposed reliefs: +X upper constant roll, -X lower tapered roll."""
    hook = _mouth_hook(spec, dimensions)
    inner = spec.half_width - dimensions.side_wall - .02
    outer = spec.half_width - 6.3004
    ledge_start = spec.depth - dimensions.pocket_front_offset
    channel_inner = spec.half_width - dimensions.channel_inner_inset
    ledge = Solid.make_box(dimensions.channel_inner_inset - 7.1162,
                           spec.depth + .1 - ledge_start,
                           POCKET_HOOK_TOP - POCKET_LEDGE_HEIGHT,
                           Plane(origin=(channel_inner, ledge_start,
                                         dimensions.pocket_floor + POCKET_LEDGE_HEIGHT)))
    parts = []
    for upper in (False, True):
        if upper:
            profile = Face(_pocket_wire(inner, dimensions.pocket_roll, spec, dimensions))
            blend = Solid.extrude(profile, (outer-inner, 0, 0))
        else:
            # A .05 terminal radius avoids a collapsed conical loft edge.
            minimum_radius = .05
            apex = spec.half_width - 7.3740
            end = apex - minimum_radius / dimensions.pocket_roll * (apex - inner)
            tapered = Solid.make_loft([_pocket_wire(inner, dimensions.pocket_roll, spec, dimensions),
                                       _pocket_wire(end, minimum_radius, spec, dimensions)], ruled=True)
            tip = Solid.extrude(Face(_pocket_wire(end, minimum_radius, spec, dimensions)), (outer-end, 0, 0))
            blend = tapered.fuse(tip).clean()
        bounded = [*hook.intersect(blend), *hook.intersect(ledge)]
        parts.extend(_place_mouth_feature(part, upper, tier_z) for part in bounded)
    return parts


def _mouth_supports(spec, dimensions, tier_z):
    """Removable webs under both mouth ledges, rooted in the pocket rear wall.

    Print growth is +Y. The web ends short of the overhanging ledge; two
    narrow teeth cross the final gap. The inner tooth straddles the runner
    wall junction, supporting the small bridge that previously started on
    another bridge. Both webs can be reached through the open runner mouth.
    """
    thickness = dimensions.pocket_support_thickness
    if thickness == 0:
        return []
    ledge_start = spec.depth - dimensions.pocket_front_offset
    back = ledge_start - dimensions.pocket_length
    inner = spec.half_width - dimensions.channel_inner_inset
    tooth = dimensions.pocket_support_tooth
    x0 = inner - tooth / 2
    # Keep the full web clear of the rolled hook wall for easy removal.
    x1 = spec.half_width - 7.1162 - .6
    if 2 * tooth >= x1 - x0:
        raise ValueError('pocket_support_tooth must leave a gap between the contacts')
    top = dimensions.pocket_floor + POCKET_LEDGE_HEIGHT - .15
    sheet_end = ledge_start - dimensions.pocket_support_gap
    sheet = Solid.make_box(x1 - x0, sheet_end - back + .02, thickness,
                           Plane(origin=(x0, back - .02, top - thickness)))
    teeth = [Solid.make_box(tooth, dimensions.pocket_support_gap + .04, thickness,
                            Plane(origin=(x, sheet_end - .02, top - thickness)))
             for x in (x0, x1 - tooth)]
    support = sheet.fuse(*teeth).clean()
    return [_place_mouth_feature(support, upper, tier_z) for upper in (False, True)]


def _tier_cutters(spec, dimensions, tier_z, *, stopper_chamfer_sides=(-1, 1)):
    """Repeat the same runner, bore and stopped-slot sections at every tier."""
    cutters = []
    inner = spec.half_width - dimensions.channel_inner_inset
    outer = spec.half_width - dimensions.channel_outer_inset
    cavity = spec.half_width - dimensions.side_wall
    center_y = spec.depth / 2 + dimensions.stopper_center_offset
    center_z = tier_z + dimensions.stopper_center_z
    for side in (-1, 1):
        runner = _runner_profile(dimensions.back_wall, tier_z + dimensions.channel_floor,
                                 tier_z + dimensions.channel_ceiling, dimensions.channel_back_radius,
                                 spec.depth, dimensions.channel_mouth_radius,
                                 lambda y, z: (side * inner, y, z))
        cutters.append(Solid.extrude(runner, (side * (outer-inner), 0, 0)))
        opening_start = side * (cavity - .01)
        opening = _runner_profile(dimensions.runner_opening_start,
                                  tier_z + dimensions.runner_opening_floor,
                                  tier_z + dimensions.runner_opening_ceiling,
                                  dimensions.runner_opening_radius, spec.depth,
                                  dimensions.channel_mouth_radius,
                                  lambda y, z: (opening_start, y, z))
        cutters.append(Solid.extrude(opening, (side * (inner+.01) - opening_start, 0, 0)))
        bore_x = side * (spec.half_width - dimensions.bore_inset)
        for z in (dimensions.bore_lower_z, dimensions.bore_upper_z):
            cutters.append(Solid.make_cylinder(dimensions.bore_entry_radius,
                                               dimensions.bore_entry_depth,
                                               Plane(origin=(bore_x, 0, tier_z+z), z_dir=(0, 1, 0))))
            cutters.append(Solid.make_cone(dimensions.bore_entry_radius, dimensions.bore_radius,
                                           dimensions.bore_taper_depth,
                                           Plane(origin=(bore_x, dimensions.bore_entry_depth, tier_z+z),
                                                 z_dir=(0, 1, 0))))
            start = dimensions.bore_entry_depth + dimensions.bore_taper_depth
            cutters.append(Solid.make_cylinder(dimensions.bore_radius, dimensions.bore_depth-start,
                                               Plane(origin=(bore_x, start, tier_z+z), z_dir=(0, 1, 0))))
        slot = Face(_slot_wire(side * (outer-.01), center_y, center_z, dimensions))
        cutters.append(Solid.extrude(slot, (side * (dimensions.channel_outer_inset+.1), 0, 0)))
        if side in stopper_chamfer_sides:
            cutters.append(Solid.make_loft([
                _slot_wire(side * (spec.half_width-dimensions.stopper_chamfer), center_y, center_z, dimensions),
                _slot_wire(side * (spec.half_width+.01), center_y, center_z, dimensions,
                           dimensions.stopper_chamfer+.01),
            ], ruled=True))
    cutters.extend(_mouth_pockets(spec, dimensions, tier_z))
    return cutters


def _divider_access(spec, dimensions, tier_z):
    """Rear-fed center stop passage with a circular entry flare.

    The constant-width tunnel meets the opposing lateral capsule slots. Those
    slots provide its rounded closed end; exterior slot chamfers are omitted
    inside the shared divider. The passage deliberately opens through the back.
    """
    width, radius = dimensions.divider_access_width, dimensions.divider_access_entry_radius
    if not 0 < width < 2 * dimensions.channel_outer_inset or not 0 < radius < 10:
        raise ValueError('Divider access must retain side walls and a compact positive entry radius')
    center = tier_z + dimensions.stopper_center_z
    floor, ceiling = center - dimensions.stopper_height / 2, center + dimensions.stopper_height / 2
    end = spec.depth / 2 + dimensions.stopper_center_offset
    point = lambda y, z: (-width / 2, y, z)
    diagonal = radius / sqrt(2)
    profile = Face(Wire([
        Edge.make_three_point_arc(point(0, floor-radius),
                                  point(radius-diagonal, floor-radius+diagonal), point(radius, floor)),
        Edge.make_line(point(radius, floor), point(end, floor)),
        Edge.make_line(point(end, floor), point(end, ceiling)),
        Edge.make_line(point(end, ceiling), point(radius, ceiling)),
        Edge.make_three_point_arc(point(radius, ceiling),
                                  point(radius-diagonal, ceiling+radius-diagonal), point(0, ceiling+radius)),
        Edge.make_line(point(0, ceiling+radius), point(0, floor-radius)),
    ]))
    return Solid.extrude(profile, (width, 0, 0))


def build_shell(spec: ModuleSpec = DEFAULT_SPEC,
                dimensions: ShellDimensions = DEFAULT_DIMENSIONS):
    """Build a smooth native sleeve; size moves features without stretching them."""
    shell = build_envelope(spec, dimensions.envelope)
    # L² keeps the L outside envelope and stacking banks, with two complete
    # S drawer interfaces. Cutting both bays from one envelope leaves a shared
    # divider; it does not introduce exterior ears or connectors inside it.
    # Full-height cavities let the same housing accept tall drawers or stacked
    # short drawers. Runner and mouth interfaces already repeat on every tier.
    bay = ModuleSpec(spec.drawer_family, spec.depth_units, spec.height_units,
                     spec.module_rear)
    cavity_half_width = bay.half_width - dimensions.side_wall
    cavity = _rounded_rect(-cavity_half_width, dimensions.skin,
                           cavity_half_width, bay.height-dimensions.skin,
                           dimensions.cavity_corner_radius,
                           lambda x, z: (x, dimensions.back_wall, z))
    cavity_cutter = Solid.extrude(cavity, (0, spec.depth-dimensions.back_wall+1, 0))
    cutters = []
    for center in spec.drawer_centers:
        sides = (-1, 1) if spec.drawer_columns == 1 else (-1,) if center < 0 else (1,)
        bay_cutters = [cavity_cutter]
        for tier_z in bay.tier_offsets:
            bay_cutters.extend(_tier_cutters(bay, dimensions, tier_z, stopper_chamfer_sides=sides))
        cutters.extend(cutter.translate((center, 0, 0)) for cutter in bay_cutters)
    if spec.drawer_columns == 2:
        cutters.extend(_divider_access(spec, dimensions, tier_z) for tier_z in spec.tier_offsets)
    for bank_x in spec.bank_centers:
        cutters.extend(_rear_notches(spec, dimensions, bank_x))
        cutters.extend(_central_recesses(spec, dimensions, bank_x))
    # L's lock sits between its two stacking banks. Keep their catches and
    # add the same lower/upper retaining recesses at the lock centerline.
    if spec.family == 'L' and spec.drawer_columns == 1:
        cutters.extend(_central_recesses(spec, dimensions, 0))
    shell = shell.cut(*cutters).clean()
    supports = [support.translate((center, 0, 0))
                for center in spec.drawer_centers for tier_z in bay.tier_offsets
                for support in _mouth_supports(bay, dimensions, tier_z)]
    return shell.fuse(*supports).clean() if supports else shell
