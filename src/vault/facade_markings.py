"""Native padlock inlays in the facade's common front datum (millimeters)."""
from build123d import Edge, Face, Solid, Wire

from .facade import rectangle

INLAY_DEPTH = .6
FRONT_Y = 10.
# Both marks stay beside the bottom-tier lock on every facade size.
MARK_CENTERS = {'locked': (-27., 32.), 'unlocked': (-27., 15.)}


def lock_icon(*, unlocked=False):
    """A filled lock body and a 0.8 mm U shackle, made from lines and arcs."""
    y = FRONT_Y - INLAY_DEPTH
    body = Solid.extrude(rectangle(-2.4, -2.7, 2.4, .3, .4, y), (0, INLAY_DEPTH, 0))
    # Shift an open shackle to the right and lift its free end above the body.
    shift = 1.6 if unlocked else 0.
    end = 1.1 if unlocked else 0.
    p = lambda x, z: (x + shift, y, z)
    edges = [Edge.make_line(p(-1.8, 0), p(-1.8, 1.6)),
             Edge.make_three_point_arc(p(-1.8, 1.6), p(0, 3.4), p(1.8, 1.6)),
             Edge.make_line(p(1.8, 1.6), p(1.8, end)),
             Edge.make_line(p(1.8, end), p(1., end)),
             Edge.make_line(p(1., end), p(1., 1.6)),
             Edge.make_three_point_arc(p(1., 1.6), p(0, 2.6), p(-1., 1.6)),
             Edge.make_line(p(-1., 1.6), p(-1., 0)),
             Edge.make_line(p(-1., 0), p(-1.8, 0))]
    # The open shackle's left leg remains rooted in the body.
    return body.fuse(Solid.extrude(Face(Wire(edges)), (0, INLAY_DEPTH, 0))).clean()


def build_facade_materials(facade):
    """Split a finished facade into primary body and registered secondary inlays.

    No reference assets are read. The union retains the original exterior and
    mating geometry; the thin facade retains 0.2 mm of primary skin behind ink.
    """
    materials = {}
    for name, (x, z) in MARK_CENTERS.items():
        icon = lock_icon(unlocked=name == 'unlocked').translate((x, 0, z))
        if abs(sum(s.volume for s in icon.intersect(facade)) - icon.volume) > 1e-5:
            raise ValueError(f'{name} icon is outside the facade skin')
        materials[name] = {'shape': icon, 'role': 'secondary', 'color': '#303030'}
    body = facade.cut(*(part['shape'] for part in materials.values())).clean()
    materials = {'body': {'shape': body, 'role': 'primary', 'color': '#f2f0eb'}, **materials}
    for name, part in materials.items():
        shape = part['shape']
        if not shape.is_valid or len(shape.solids()) != 1 or len(shape.shells()) != 1:
            raise ValueError(f'{name}: expected one valid material solid')
    return materials
