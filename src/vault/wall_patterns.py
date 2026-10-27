"""Native waffle and Miura walls inside the original module envelope.

Recessed reliefs retain the inner surfaces, with two-line valley webs and
thicker crests. Corrugated panels relieve both faces using normal offsets for
two-line walls. Both preserve solid structural lands. No purchased geometry
or mesh is used to construct the patterns.
"""
from dataclasses import dataclass, replace
from math import ceil, floor, sqrt

from build123d import Face, Kind, Shell, Solid, Wire

from .connectors import build_connectors, build_connector_cutters
from .shell import _rounded_rect


@dataclass(frozen=True)
class PatternPanel:
    """Local (u, v, inward depth) frame and protected rectangular footprints."""

    face: str
    datum: float
    bounds: tuple[float, float, float, float]
    keepouts: tuple[tuple[float, float, float, float], ...] = ()
    origin_depth: float = 0.0
    direction: int = 1

    def point(self, u, v, depth):
        depth = self.origin_depth + self.direction * depth
        if self.face == 'top':
            return (u, v, self.datum - depth)
        if self.face == 'bottom':
            return (u, v, depth)
        if self.face == 'right':
            return (self.datum - depth, v, u)
        return (-self.datum + depth, v, u)


LAND = 3.0
REAR_LAND = 8.0
FRONT_LAND = 12.0


def pattern_panels(spec, dimensions, connector_parameters):
    """Safe flat skins, with lands derived from the actual native features.

    Bounding footprints deliberately protect entire connector roots, including
    the space between individual teeth. Inter-tier webs and the L² divider
    remain full thickness. Side panels avoid the runner floors and ceilings.
    """
    d = dimensions
    rear = max(REAR_LAND, d.back_wall + LAND,
               d.rear_notch_depth + LAND)
    front = spec.depth - max(FRONT_LAND,
                            d.pocket_front_offset + d.pocket_length + LAND,
                            d.catch_front_offset + LAND)
    stop_y = spec.depth / 2 + d.stopper_center_offset
    stop_half = d.stopper_length / 2 + d.stopper_chamfer + .01 + LAND
    panels = []
    for side in ('left', 'right'):
        for tier in spec.tier_offsets:
            lo = max(d.envelope.corner_height + LAND,
                     tier + d.channel_floor + LAND)
            hi = min(spec.height - d.envelope.corner_height - LAND,
                     tier + d.channel_ceiling - LAND)
            if hi > lo:
                # A continuous solid band carries the stopper's insertion and
                # drawer load; its entire native chamfer is inside this band.
                bore_radius = max(d.bore_entry_radius, d.bore_radius)
                bore_keepouts = tuple((offset + z - bore_radius - LAND, -1,
                                       offset + z + bore_radius + LAND,
                                       d.bore_depth + LAND)
                                      for offset in spec.tier_offsets
                                      for z in (d.bore_lower_z, d.bore_upper_z))
                panels.append(PatternPanel(side, spec.half_width,
                    (lo, rear, hi, front),
                    ((lo - 1, stop_y - stop_half, hi + 1, stop_y + stop_half),
                     *bore_keepouts)))
    if spec.pattern_faces == 'sides':
        return panels

    features = build_connectors(spec, connector_parameters)
    cutters = build_connector_cutters(spec, connector_parameters)
    extent = spec.half_width - d.envelope.corner_width - LAND
    for face in ('bottom', 'top'):
        keepouts = []
        for feature in [*features, *cutters]:
            box = feature.bounding_box()
            belongs = box.min.Z < 0 if face == 'bottom' else box.max.Z > spec.height
            if belongs:
                keepouts.append((box.min.X - LAND, box.min.Y - LAND,
                                 box.max.X + LAND, box.max.Y + LAND))
        if spec.drawer_columns == 2:
            keepouts.append((-d.side_wall - LAND, rear - 1,
                             d.side_wall + LAND, front + 1))
        # Normally these footprints lie in the unpatterned corner bands.
        # Derive them anyway so custom bore positions/radii remain protected.
        bay_half = spec.width / (2 * spec.drawer_columns)
        radius = max(d.bore_entry_radius, d.bore_radius)
        for tier in spec.tier_offsets:
            for z in (tier + d.bore_lower_z, tier + d.bore_upper_z):
                near_skin = z-radius < d.skin+LAND if face == 'bottom' else z+radius > spec.height-d.skin-LAND
                if near_skin:
                    for center in spec.drawer_centers:
                        for side in (-1, 1):
                            x = center + side * (bay_half - d.bore_inset)
                            keepouts.append((x-radius-LAND, -1,
                                             x+radius+LAND, d.bore_depth+LAND))
        panels.append(PatternPanel(face, spec.height,
                                  (-extent, rear, extent, front), tuple(keepouts)))
    return panels


def _rect_wire(panel, bounds, depth):
    u0, v0, u1, v1 = bounds
    return Wire.make_polygon([panel.point(u, v, depth) for u, v in
                              ((u0, v0), (u1, v0), (u1, v1), (u0, v1))], close=True)


def _inset(bounds, amount):
    u0, v0, u1, v1 = bounds
    return (u0 + amount, v0 + amount, u1 - amount, v1 - amount)


def _overlaps(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _unobstructed_pieces(bounds, keepouts):
    """Split a rectangle around structural lands without crossing any of them."""
    pieces = [bounds]
    for keepout in keepouts:
        next_pieces = []
        for a, b, c, d in pieces:
            if not _overlaps((a, b, c, d), keepout):
                next_pieces.append((a, b, c, d))
                continue
            x0, y0, x1, y1 = keepout
            l, r, lo, hi = max(a, x0), min(c, x1), max(b, y0), min(d, y1)
            next_pieces.extend(piece for piece in
                ((a, b, l, d), (r, b, c, d), (l, b, r, lo), (l, hi, r, d))
                if piece[2]-piece[0] > 1e-7 and piece[3]-piece[1] > 1e-7)
        pieces = next_pieces
    return pieces


def _waffle_cutters(panel, spec):
    """Rounded-square dimples with broad sloping shoulders and flat valleys."""
    pitch, depth = spec.pattern_pitch, spec.pattern_depth
    rib = 2 * spec.pattern_line_width
    u0, v0, u1, v1 = panel.bounds
    # Narrow panels receive rectangular cells at the requested longitudinal
    # pitch, so a large pitch does not silently omit the left/right walls.
    half_u = min(pitch - rib, u1-u0-rib) / 2
    half_v = min(pitch - rib, v1-v0-rib) / 2
    half = min(half_u, half_v)
    shoulder = max(2 * depth, pitch * .18)
    # Small pitches retain a positive rounded bottom and a <=45-degree ramp.
    shoulder = min(shoulder, half - .6)
    radius = min(2.0, half / 3)
    count_u, count_v = floor((u1-u0) / pitch), floor((v1-v0) / pitch)
    # A narrow side panel still receives one complete cell if it fits.
    count_u = max(count_u, int(half_u > shoulder))
    count_v = max(count_v, int(half_v > shoulder))
    candidates = []
    for i in range(count_u):
        u = (u0 + u1) / 2 + (i - (count_u-1)/2) * pitch
        for j in range(count_v):
            v = (v0 + v1) / 2 + (j - (count_v-1)/2) * pitch
            candidates.append((u-half_u, v-half_v, u+half_u, v+half_v))
    selected = [bounds for bounds in candidates
                if not any(_overlaps(bounds, keepout) for keepout in panel.keepouts)]
    if not selected:
        # Large cells can meet every connector on a short module's top. Keep
        # the requested grid but trim those cells to available rectangular
        # lands, rather than silently leaving a requested face unpatterned.
        for bounds in candidates:
            pieces = [piece for piece in _unobstructed_pieces(bounds, panel.keepouts)
                      if min(piece[2]-piece[0], piece[3]-piece[1]) >= 2*depth+1.2]
            if pieces:
                selected.append(max(pieces, key=lambda p: (p[2]-p[0])*(p[3]-p[1])))
    for bounds in selected:
        local_shoulder = min(shoulder, min(bounds[2]-bounds[0], bounds[3]-bounds[1])/2-.6)
        wires = []
        # A short native ruled loft keeps predictable slopes and rounded
        # corners. The outside extension avoids coincident cut faces.
        for inward, inset in ((-.3, 0), (0, 0), (depth, local_shoulder)):
            a, b, c, e = _inset(bounds, inset)
            r = min(radius, (c-a)/3, (e-b)/3)
            wires.append(_rounded_rect(a, b, c, e, r,
                lambda x, y, inward=inward: panel.point(x, y, inward)).outer_wire())
        yield Solid.make_loft(wires, ruled=True)


def _miura_field(panel, spec):
    """A connected zigzag field of planar parallelograms, not diamond pits.

    Alternating row offsets turn the mountain/valley folds into chevrons.
    Facets are native planar faces sewn into one closed cutting solid. This
    rigid relief uses the Miura crease layout; it is not a folding mechanism.
    """
    step = spec.pattern_pitch / 2
    u0, v0, u1, v1 = panel.bounds
    nu, nv = ceil((u1-u0)/step) + 4, ceil((v1-v0)/step) + 2
    start_u, start_v = u0 - 2*step, v0 - step
    grid = [[(start_u + i*step + (j % 2)*step/2, start_v + j*step,
              spec.pattern_depth if i % 2 else 0.0)
             for i in range(nu+1)] for j in range(nv+1)]
    faces = []

    def face(points):
        return Face(Wire.make_polygon([panel.point(*point) for point in points], close=True))

    for j in range(nv):
        for i in range(nu):
            faces.append(face([grid[j][i], grid[j][i+1], grid[j+1][i+1], grid[j+1][i]]))
    boundary = [*grid[0], *[row[-1] for row in grid[1:]],
                *reversed(grid[-1][:-1]), *[row[0] for row in reversed(grid[1:-1])]]
    outside = [(u, v, -.3) for u, v, _ in boundary]
    faces.append(face(list(reversed(outside))))
    for index, a in enumerate(boundary):
        next_index = (index + 1) % len(boundary)
        faces.append(face([a, outside[index], outside[next_index], boundary[next_index]]))
    field = Solid(Shell(faces))
    if field.volume < 0:
        field.wrapped.Reverse()
    if not field.is_valid:
        raise ValueError('Invalid native Miura field')
    return field


def _panel_mask(panel, depth):
    """Removal envelope with a 2:1 ramp into full-thickness boundary lands."""
    transition = 2*depth
    u0, v0, u1, v1 = panel.bounds
    if min(u1-u0, v1-v0) <= 2*transition:
        raise ValueError('Pattern transition does not fit the protected wall panel')
    # This tapered clipping volume returns the relief to the original skin
    # over a 2:1 run at every panel edge, including partial end cells.
    mask = Solid.make_loft([_rect_wire(panel, panel.bounds, -.3),
                            _rect_wire(panel, panel.bounds, 0),
                            _rect_wire(panel, _inset(panel.bounds, transition), depth)], ruled=True)
    keepouts = [Solid.make_loft([
        _rect_wire(panel, bounds, -.4), _rect_wire(panel, bounds, 0),
        _rect_wire(panel, _inset(bounds, -transition-.2), depth+.1)], ruled=True)
        for bounds in panel.keepouts if _overlaps(panel.bounds, bounds)]
    return mask.cut(*keepouts) if keepouts else mask


def _miura_cutters(panel, spec):
    return _miura_field(panel, spec).intersect(_panel_mask(panel, spec.pattern_depth)).solids()


def miura_normal_offset(spec):
    """Axial separation giving exactly two lines normal to every Miura facet."""
    slope = spec.pattern_depth / (spec.pattern_pitch / 2)
    return 2 * spec.pattern_line_width * sqrt(1 + 1.25*slope*slope)


def corrugated_miura_spec(spec, wall):
    """Fit a normally thickened, sharply mitred fold inside the original skin."""
    if spec.pattern_depth + miura_normal_offset(spec) <= wall:
        return spec
    low, high = 0., spec.pattern_depth
    for _ in range(48):
        depth = (low+high)/2
        slope = depth / (spec.pattern_pitch/2)
        separation = 2*spec.pattern_line_width * sqrt(1 + 1.25*slope*slope)
        if depth + separation <= wall:
            low = depth
        else:
            high = depth
    return replace(spec, pattern_depth=low)


def _corrugated_inner_cutters(panel, spec, dimensions, outside):
    """Offset the outer relief normally by two lines, then relieve the inside.

    ARC offsets preserve normal wall thickness at dimple shoulders. Miura
    facets have equal gradient magnitudes and use exact parallel plane offsets
    with mitred folds. An uncorrected translation would make slopes too thin.
    Offsetting the *uncropped* Miura field deliberately thickens the transition
    lands; inner and outer clipping share the same protected feature footprints.
    """
    wall = dimensions.skin if panel.face in ('top', 'bottom') else dimensions.channel_outer_inset
    thickness = 2 * spec.pattern_line_width
    if spec.wall_pattern == 'miura':
        a, b = panel.point(0, 0, 0), panel.point(0, 0, miura_normal_offset(spec))
        offsets = [_miura_field(panel, spec).translate(tuple(y-x for x, y in zip(a, b)))]
    else:
        offsets = [source.offset_3d([], thickness, kind=Kind.ARC) for source in outside]
    for shape in offsets:
        if not shape.is_valid:
            raise ValueError('Invalid normal offset for corrugated wall')
    # The flat part of the outer skin also gets two lines. Unioning that
    # offset with the dimple offsets is equivalent to clipping this block.
    inside = Solid.make_loft([_rect_wire(panel, panel.bounds, thickness),
                              _rect_wire(panel, panel.bounds, wall+.3)], ruled=True)
    inside = inside.cut(*offsets)
    inner_frame = replace(panel, origin_depth=wall, direction=-1)
    mask = _panel_mask(inner_frame, wall-thickness)
    return [solid for item in inside.solids() for solid in item.intersect(mask).solids()]


def pattern_cutters(spec, dimensions, connector_parameters):
    """Return cutters and enforce the two-line minimum against native skins."""
    if spec.wall_pattern == 'plain':
        return []
    minimum = 2 * spec.pattern_line_width
    available = dimensions.channel_outer_inset
    if spec.pattern_faces == 'all':
        available = min(available, dimensions.skin)
    if spec.pattern_depth + minimum > available + 1e-9:
        raise ValueError('Pattern depth must leave two extrusion lines in the native skin')
    result = []
    for panel in pattern_panels(spec, dimensions, connector_parameters):
        panel_spec = spec
        if spec.pattern_construction == 'corrugated' and spec.wall_pattern == 'miura':
            wall = dimensions.skin if panel.face in ('top', 'bottom') else dimensions.channel_outer_inset
            panel_spec = corrugated_miura_spec(spec, wall)
        outside = list(_waffle_cutters(panel, panel_spec) if spec.wall_pattern == 'waffle'
                       else _miura_cutters(panel, panel_spec))
        if not outside:
            raise ValueError(f'Pattern cannot fit the {panel.face} panel; reduce its pitch')
        result.extend(outside)
        if spec.pattern_construction == 'corrugated':
            result.extend(_corrugated_inner_cutters(panel, panel_spec, dimensions, outside))
    if not result:
        raise ValueError('Pattern pitch does not fit the protected wall panels')
    return result


def apply_wall_pattern(part, spec, dimensions, connector_parameters, progress=None):
    if spec.wall_pattern == 'plain':
        return part
    if progress:
        progress(f'Cutting {spec.wall_pattern} wall relief; preserving mechanical lands')
    cutters = pattern_cutters(spec, dimensions, connector_parameters)
    return part.cut(*cutters).clean()
