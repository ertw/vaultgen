"""Native flush-inlaid label; font outlines are curves shared with the editor.

The readable face lies at Z=2. Print rotation about Y puts that face at Z=0.
Purchased label meshes are measurement references, never constructor inputs.
"""
from functools import lru_cache
import math

from build123d import Axis, Compound, Edge, Face, Solid, Wire

from .exports import precise_volume
from .label_config import LabelConfiguration, label_dimensions, label_font, label_layout


def label_outline(inset=0., z=0., *, family='S'):
    """Readable face: a true right semicircle and small left corners."""
    dimensions = label_dimensions(family)
    width, height = dimensions['width_mm'], dimensions['height_mm']
    corner = max(0., dimensions['corner_radius_mm']-inset)
    left, right, bottom, top = height/2, width-inset, inset, height-inset
    p = lambda x, y: (x, y, z)
    edges = [Edge.make_line(p(left, bottom), p(right-corner, bottom))]
    if corner:
        edges.append(Edge.make_three_point_arc(p(right-corner,bottom),
            p(right-corner+corner/math.sqrt(2),bottom+corner-corner/math.sqrt(2)),p(right,bottom+corner)))
    edges.append(Edge.make_line(p(right,bottom+corner),p(right,top-corner)))
    if corner:
        edges.append(Edge.make_three_point_arc(p(right,top-corner),
            p(right-corner+corner/math.sqrt(2),top-corner+corner/math.sqrt(2)),p(right-corner,top)))
    edges.extend([Edge.make_line(p(right-corner,top),p(left,top)),
                  Edge.make_three_point_arc(p(left,top),p(inset,height/2),p(left,bottom))])
    return Wire(edges).rotate(Axis.Z,180).translate((width,height,0))


@lru_cache(maxsize=256)
def _glyph_faces(character):
    """Keep every TrueType quadratic curve as an exact native Bezier edge.

    Polygon samples classify nesting only; native wires construct the faces.
    """
    from shapely.geometry import Polygon
    contours, edges, points = [], [], []
    current = start = None
    units = label_font()['units_per_em']
    for command in label_font()['glyphs'][character]['commands']:
        kind, *values = command
        vectors = [(values[i]/units, values[i+1]/units, 0.) for i in range(0,len(values),2)]
        if kind == 'M':
            current = start = vectors[0]
            edges, points = [], [current[:2]]
        elif kind == 'L':
            if current != vectors[0]:
                edges.append(Edge.make_line(current, vectors[0]))
                points.append(vectors[0][:2])
            current = vectors[0]
        elif kind in ('Q', 'C'):
            controls = [current, *vectors]
            edges.append(Edge.make_bezier(*controls))
            order = len(controls)-1
            for step in range(1,17):
                t = step/16
                points.append(tuple(sum(math.comb(order,k)*(1-t)**(order-k)*t**k*p[a]
                                        for k,p in enumerate(controls)) for a in (0,1)))
            current = vectors[-1]
        elif kind == 'Z':
            if current != start:
                edges.append(Edge.make_line(current, start))
            if edges:
                polygon = Polygon(points)
                if not polygon.is_valid or polygon.area <= 0:
                    raise ValueError(f'Invalid font outline for {character!r}')
                contours.append((Wire(edges), polygon))
    faces = []
    for wire, polygon in contours:
        depth = sum(other.area > polygon.area and other.contains(polygon.representative_point())
                    for _,other in contours)
        if depth % 2:
            continue
        holes = [candidate for candidate,other in contours
                 if other.area < polygon.area and polygon.contains(other.representative_point())
                 and sum(p.area > other.area and p.contains(other.representative_point())
                         for _,p in contours) == depth+1]
        face = Face(wire, holes)
        if not face.is_valid or face.area <= 0:
            raise ValueError(f'Invalid native font face for {character!r}')
        faces.append(face)
    return tuple(faces)


def to_print(shape, family='S'):
    """Common rigid transform: readable-face X reverses, face lands on the bed."""
    dimensions = label_dimensions(family)
    return shape.rotate(Axis.Y, 180).translate((dimensions['width_mm'],0,dimensions['thickness_mm']))


def facade_transform(family='S'):
    return [-1,0,0,0, 0,0,1,0, 0,1,0,0,
            round(32.3+label_dimensions(family)['width_mm'],6),7.92,13.8,1]


FACADE_TRANSFORM = facade_transform()


def to_facade(shape, family='S'):
    """Proper rigid placement: text up maps +Z, front normal maps outward +Y.

    (x,y,z) -> (32.3+width-x, 7.92+z, 13.8+y). The rear rim clears the
    recess floor by 0.01 mm, leaving room for an adhesive mounting choice.
    """
    placement = facade_transform(family)
    return shape.rotate(Axis.X,90).rotate(Axis.Z,180).translate(tuple(placement[12:15]))


def build_label_parts(config=None):
    """Return color groups in readable native coordinates, plus CAD checks.

    Every disconnected glyph remains a real solid. The 0.3 mm web behind the
    inlays keeps letter counters attached to the shell and bonds every color.
    """
    config = config or LabelConfiguration()
    dimensions = label_dimensions(config)
    thickness, face_depth = dimensions['thickness_mm'], dimensions['face_thickness_mm']
    body = Solid.extrude(Face(label_outline(family=config.family)), (0,0,thickness))
    if config.hollow:
        pocket = Solid.extrude(Face(label_outline(dimensions['rim_thickness_mm'],family=config.family)),
                               (0,0,thickness-face_depth))
        body = body.cut(pocket)
    uncut_volume = precise_volume(body)
    groups = {}
    for line in label_layout(config):
        if line['color'] == config.background:
            continue
        solids = groups.setdefault(line['color'], [])
        for glyph in line['glyphs']:
            for face in _glyph_faces(glyph['character']):
                positioned = face.scale(line['size']).translate((glyph['x'],line['baseline_y'],
                            thickness-dimensions['inlay_depth_mm']))
                solids.append(Solid.extrude(positioned,(0,0,dimensions['inlay_depth_mm'])))
    # Font advance widths can be narrower than the visible outline (e.g. YY,
    # accented i pairs). Union a color's overlapping glyphs before carving the
    # shell so each material is a disjoint set of solids, including at overhangs.
    groups = {color: list(solids[0].fuse(*solids[1:]).solids()) if len(solids) > 1 else solids
              for color, solids in groups.items()}
    inlays = [solid for solids in groups.values() for solid in solids]
    body = body.cut(*inlays)
    if not body.is_valid or len(body.solids()) != 1 or len(body.shells()) != 1:
        raise ValueError('Label shell must be one valid solid with connected letter counters')
    parts = {'label_body': {'shape': body, 'color': config.background, 'role': 'body'}}
    for index, (color, solids) in enumerate(groups.items(), 1):
        shape = Compound(solids)
        if not shape.is_valid or any(not s.is_valid or len(s.shells()) != 1 for s in solids):
            raise ValueError('Every text island must be a valid solid with one boundary shell')
        parts[f'label_ink_{index}'] = {'shape': shape, 'color': color, 'role': 'text'}
    volume = sum(precise_volume(item['shape']) for item in parts.values())
    if abs(volume-uncut_volume) > 1e-5:
        raise ValueError('Color volumes do not reconstruct the original label shell')
    overlaps = []
    values = list(parts.values())
    for i, first in enumerate(values):
        for second in values[i+1:]:
            common = first['shape'].intersect(second['shape'])
            overlap = sum(abs(precise_volume(s)) for s in common) if common else 0.
            overlaps.append(overlap)
            if overlap > 1e-6:
                raise ValueError(f'Label colors overlap by {overlap:g} mm³')
    return parts, {'passed': True, 'color_overlap_mm3': max(overlaps, default=0.),
                   'shell_volume_mm3': uncut_volume, 'color_volume_mm3': volume,
                   'family': config.family, 'label_dimensions': dimensions,
                   'counter_web_mm': face_depth-dimensions['inlay_depth_mm'],
                   'coordinates': 'readable-face',
                   'facade_transform': facade_transform(config),
                   'print_transform': [-1,0,0,0,0,1,0,0,0,0,-1,0,
                                       dimensions['width_mm'],0,thickness,1]}
