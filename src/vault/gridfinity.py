"""Native Gridfinity sockets integrated above the existing drawer floor.

Dimensions follow Gridfinity Rebuilt's primary construction definitions:
https://github.com/kennetek/gridfinity-rebuilt-openscad/blob/main/src/core/standard.scad
https://github.com/kennetek/gridfinity-rebuilt-openscad/blob/main/src/core/gridfinity-baseplate.scad

The 42 mm pitch, 4 mm socket corner radius and 0.7/1.8/2.15 mm
socket profile are kept at their nominal size. A 0.35 mm lower relief gives
the reference 5 mm total baseplate height. Socket cuts stop on the selected
closed drawer floor. Floorless trays retain the same thin-floor socket datum
and open each cell bottom, keeping the foundation under the grid webs.
There are no magnet or screw recesses.
"""
from dataclasses import dataclass
from math import floor

from .drawer import DrawerLayout


PITCH = 42.0
SOCKET_HEIGHT = 5.0
SOCKET_SECTIONS = (
    (0.0, 36.3, 1.15),
    (0.35, 36.3, 1.15),
    (1.05, 37.7, 1.85),
    (2.85, 37.7, 1.85),
    (5.0, 42.0, 4.0),
)


@dataclass(frozen=True)
class GridfinityLayout:
    """Whole cells and their datums in the drawer's assembly coordinates."""

    spec: object

    def __post_init__(self):
        object.__setattr__(self, '_drawer', DrawerLayout(self.spec))
        selected_floor = getattr(self.spec, 'box_floor', 0.8)
        if (type(selected_floor) not in (int, float)
                or selected_floor not in (0, 0.8, 3.0)):
            raise ValueError('Gridfinity floor must be 0, 0.8 or 3.0 mm')
        if selected_floor == 0 and getattr(self.spec, 'box_variant', 'plain') != 'gridfinity':
            raise ValueError('A floorless box requires the Gridfinity base')

    @property
    def columns(self):
        return floor((127.2 + 2 * self._drawer.width_delta) / PITCH)

    @property
    def rows(self):
        # Inset from the rear floor fillet and the front lock bevel. The
        # available length is 42*n + 2.8 mm for every supported depth.
        return floor((170.8 + self._drawer.depth_delta) / PITCH)

    @property
    def pitch(self):
        return PITCH

    @property
    def socket_height(self):
        return SOCKET_HEIGHT

    @property
    def floor_z(self):
        """Socket lower datum; floorless grids retain the thin-floor profile."""
        return 5.0 + max(.8, getattr(self.spec, 'box_floor', .8))

    @property
    def x_min(self):
        return -self.columns * PITCH / 2

    @property
    def x_max(self):
        return -self.x_min

    @property
    def y_min(self):
        return (6.3 + 177.1 + self._drawer.depth_delta - self.rows * PITCH) / 2

    @property
    def y_max(self):
        return self.y_min + self.rows * PITCH

    @property
    def centers(self):
        return tuple((self.x_min + (column + .5) * PITCH,
                      self.y_min + (row + .5) * PITCH)
                     for row in range(self.rows) for column in range(self.columns))

    def notes(self):
        return {
            'columns': self.columns, 'rows': self.rows, 'pitch_mm': self.pitch,
            'socket_height_mm': self.socket_height,
            'floor_z_mm': self.floor_z,
            'socket_base_z_mm': self.floor_z,
            'closed_floor_mm': getattr(self.spec, 'box_floor', .8),
            'foundation_thickness_mm': self.floor_z - 5.0,
            'grid_bounds_xy_mm': [self.x_min, self.y_min, self.x_max, self.y_max],
            'magnet_holes': False,
        }


def _section_wire(size, radius, z):
    from .shell import _rounded_rect
    return _rounded_rect(-size/2, -size/2, size/2, size/2, radius,
                         lambda x, y: (x, y, z)).outer_wire()


def socket_cutter():
    """A nominal rounded, chamfered socket at the origin with floor Z=0."""
    from build123d import Solid
    # Ruled lofts preserve the straight and 45-degree profile segments.
    sections = [_section_wire(size, radius, z)
                for z, size, radius in SOCKET_SECTIONS]
    return Solid.make_loft(sections, ruled=True)


def build_gridfinity_base(spec):
    """Return the socket web in assembly space, joined to the tray foundation."""
    from build123d import Solid
    from .shell import _rounded_rect

    layout = GridfinityLayout(spec)
    if layout.columns < 1 or layout.rows < 1:
        raise ValueError('Drawer has no room for a complete Gridfinity cell')
    # A tenth of a millimeter overlaps the tray foundation for robust union.
    # Closed-floor variants retain it; the floorless hook subsequently opens
    # the cell bottoms through this skin and the underlying drawer floor.
    face = _rounded_rect(layout.x_min, layout.y_min, layout.x_max,
                         layout.y_max, 4.0,
                         lambda x, y: (x, y, layout.floor_z - .1))
    base = Solid.extrude(face, (0, 0, SOCKET_HEIGHT + .1))
    cutter = socket_cutter()
    cutters = [cutter.translate((x, y, layout.floor_z)) for x, y in layout.centers]
    base = base.cut(*cutters).clean()
    if not base.is_valid or len(base.solids()) != 1:
        raise ValueError('Expected one valid Gridfinity base solid')
    return base


def apply_gridfinity_floorless(part, spec):
    """Open every cell through the tray floor, after the socket web is fused.

    The lower socket footprint continues through the bed face. Material below
    the webs and around the grid stays intact to connect every web to the tray
    walls. Keeping the socket datum lets nominal feet seat on their chamfers.
    """
    if getattr(spec, 'box_floor', .8) != 0:
        return part
    from build123d import Face, Solid

    layout = GridfinityLayout(spec)
    _, size, radius = SOCKET_SECTIONS[0]
    # Overlap the lower socket void as well as the base's .1 mm union skin,
    # avoiding coplanar cuts at either end of the preserved mating profile.
    bottom = 4.9
    opening = Solid.extrude(Face(_section_wire(size, radius, bottom)),
                            (0, 0, layout.floor_z-bottom+.01))
    cutters = [opening.translate((x, y, 0)) for x, y in layout.centers]
    result = part.cut(*cutters).clean()
    if not result.is_valid or len(result.solids()) != 1 or len(result.shells()) != 1:
        raise ValueError('Expected one valid floorless Gridfinity box solid')
    return result
