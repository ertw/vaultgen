"""Bounded drawer-bin drawings, with no CAD imports at the HTTP boundary."""
from dataclasses import dataclass
import hashlib
import json

from .gridfinity import GridfinityLayout, PITCH
from .drawer import DrawerLayout
from .spec import ModuleSpec


GRID_COLUMNS = {family: GridfinityLayout(ModuleSpec(family)).columns for family in ('S','M','L')}
DRAWER_COLUMNS = {'S': 3, 'M': 4, 'L': 6}
LINE_WIDTH = .65
HEIGHTS = {1: 28.0, 2: 77.0}
DRAWER_BIN_FLOOR = 1.2
DRAWER_CLEARANCE = .25
DRAWER_RIM_CLEARANCE = 1.0


@dataclass(frozen=True, order=True)
class BinDivider:
    """x is a vertical grid line; y is a horizontal grid line."""
    axis: str
    x: int
    y: int

    def adjacent_cells(self):
        return ((self.x-1, self.y), (self.x, self.y)) if self.axis == 'x' else (
            (self.x, self.y-1), (self.x, self.y))

    def as_dict(self):
        return {'axis': self.axis, 'x': self.x, 'y': self.y}


@dataclass(frozen=True)
class BinConfiguration:
    family: str = 'S'
    depth_units: int = 4
    height_units: int = 1
    cells: tuple[tuple[int, int], ...] | None = None
    dividers: tuple[BinDivider, ...] = ()
    wall_pattern: str = 'plain'
    wall_perimeters: int = 2
    part: str = 'gridfinity_bins'
    container_type: str = 'gridfinity'
    drawer_floor: float = .8

    def __post_init__(self):
        if self.part != 'gridfinity_bins':
            raise ValueError('Expected a Gridfinity bin configuration')
        if self.container_type not in ('gridfinity', 'drawer'):
            raise ValueError('Container type must be gridfinity or drawer')
        if type(self.drawer_floor) not in (int, float) or self.drawer_floor not in (.8, 3.):
            raise ValueError('The existing plain drawer floor must be 0.8 or 3 mm')
        object.__setattr__(self, 'drawer_floor', float(self.drawer_floor))
        if self.container_type == 'gridfinity' and self.drawer_floor != .8:
            raise ValueError('Existing drawer floor applies only to drawer-fit boxes')
        if not isinstance(self.family, str) or self.family not in GRID_COLUMNS:
            raise ValueError('Choose drawer family S, M, or L')
        if type(self.depth_units) is not int or self.depth_units not in range(3, 8):
            raise ValueError('Drawer depth must be 3–7 units')
        if type(self.height_units) is not int or self.height_units not in HEIGHTS:
            raise ValueError('Drawer height must be 1F or 2F')
        if self.wall_pattern not in ('plain', 'miura'):
            raise ValueError('Bin wall pattern must be plain or miura')
        if type(self.wall_perimeters) is not int or self.wall_perimeters not in (1, 2):
            raise ValueError('Choose one or two wall perimeters for a 0.6 mm nozzle')
        cells = self.cells
        if cells is None:
            cells = [(x, y) for y in range(self.rows) for x in range(self.columns)]
        if not isinstance(cells, (list, tuple)) or not 1 <= len(cells) <= self.columns*self.rows:
            raise ValueError('Paint at least one cell inside the selected drawer grid')
        normalized = []
        for cell in cells:
            if (not isinstance(cell, (tuple, list)) or len(cell) != 2
                    or any(type(value) is not int for value in cell)
                    or not (0 <= cell[0] < self.columns and 0 <= cell[1] < self.rows)):
                raise ValueError('Each selected cell must have integer x/y coordinates inside the drawer grid')
            normalized.append(tuple(cell))
        selected = set(normalized)
        if len(selected) != len(normalized):
            raise ValueError('Selected cells must not be repeated')
        object.__setattr__(self, 'cells', tuple(sorted(selected, key=lambda p: (p[1], p[0]))))
        if not isinstance(self.dividers, (list, tuple)) or len(self.dividers) > 71:
            raise ValueError('Choose dividers on internal edges of the selected drawer grid')
        dividers = []
        for divider in self.dividers:
            if isinstance(divider, dict) and set(divider) == {'axis', 'x', 'y'}:
                divider = BinDivider(**divider)
            if (not isinstance(divider, BinDivider) or divider.axis not in ('x', 'y')
                    or type(divider.x) is not int or type(divider.y) is not int
                    or not all(cell in selected for cell in divider.adjacent_cells())):
                raise ValueError('Each divider must lie between two painted cells')
            dividers.append(divider)
        if len(set(dividers)) != len(dividers):
            raise ValueError('Dividers must not be repeated')
        object.__setattr__(self, 'dividers', tuple(sorted(dividers)))

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError('Expected a Gridfinity bin configuration with no unknown fields')
        # Null is not an omitted drawing: reject accidental cleared requests.
        if 'cells' in value and value['cells'] is None:
            raise ValueError('Selected cells must be an array')
        try:
            return cls(**value)
        except TypeError as error:
            raise ValueError('Invalid Gridfinity bin configuration') from error

    def as_dict(self):
        result = {'part': self.part, 'family': self.family, 'depth_units': self.depth_units,
                'height_units': self.height_units, 'cells': [list(cell) for cell in self.cells],
                'dividers': [divider.as_dict() for divider in self.dividers],
                'wall_pattern': self.wall_pattern, 'wall_perimeters': self.wall_perimeters}
        # Retain the identity of existing Gridfinity drawings and saved jobs.
        if self.container_type == 'drawer':
            result.update(container_type='drawer', drawer_floor=self.drawer_floor)
        return result

    @property
    def columns(self):
        return (DRAWER_COLUMNS if self.container_type == 'drawer' else GRID_COLUMNS)[self.family]

    @property
    def rows(self):
        return self.depth_units

    @property
    def wall_thickness_mm(self):
        return LINE_WIDTH*self.wall_perimeters

    @property
    def height_mm(self):
        if self.container_type == 'drawer':
            return (42.5 + 48*(self.height_units-1) - (5+self.drawer_floor)
                    - DRAWER_CLEARANCE - DRAWER_RIM_CLEARANCE)
        return HEIGHTS[self.height_units]

    @property
    def width_mm(self):
        if self.container_type == 'drawer':
            return 127.2 + 2*DrawerLayout(ModuleSpec(self.family,self.depth_units,self.height_units)).width_delta
        return self.columns*PITCH

    @property
    def depth_mm(self):
        if self.container_type == 'drawer':
            # Front limit protects the center lock opening. Unlike the
            # Gridfinity pitch, this is the native plain drawer's cavity.
            return 172.8 + DrawerLayout(ModuleSpec(self.family,self.depth_units,self.height_units)).depth_delta
        return self.rows*PITCH

    @property
    def pitch_x_mm(self):
        return self.width_mm/self.columns

    @property
    def pitch_y_mm(self):
        return self.depth_mm/self.rows

    @property
    def floor_top_mm(self):
        return DRAWER_BIN_FLOOR if self.container_type == 'drawer' else 7.

    @property
    def foot_height_mm(self):
        return 0. if self.container_type == 'drawer' else 4.75

    @property
    def corner_radius_mm(self):
        return 3.25 if self.container_type == 'drawer' else 3.75

    @property
    def components(self):
        remaining, groups = set(self.cells), []
        while remaining:
            seed = min(remaining, key=lambda p: (p[1], p[0]))
            remaining.remove(seed)
            pending, group = [seed], []
            while pending:
                x, y = pending.pop()
                group.append((x, y))
                for cell in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
                    if cell in remaining:
                        remaining.remove(cell)
                        pending.append(cell)
            groups.append(tuple(sorted(group, key=lambda p: (p[1], p[0]))))
        return tuple(groups)

    @property
    def parts(self):
        return ('gridfinity_bins',)

    @property
    def key(self):
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True).encode()).hexdigest()

    @property
    def slug(self):
        suffix = 'drawer_bins' if self.container_type == 'drawer' else 'gridfinity_bins'
        return f'{self.family.lower()}{self.depth_units}_{self.height_units}f_{self.key[:16]}_{suffix}'

    @property
    def name(self):
        kind = 'drawer-fit boxes' if self.container_type == 'drawer' else 'Gridfinity bins'
        return f'{self.family}{self.depth_units} {self.height_units}F {kind}'


def bin_layout(config):
    """Resolved dimensions and registration shared by exports and the editor."""
    return {'columns': config.columns, 'rows': config.rows,
            'container_type': config.container_type,
            'pitch_mm': PITCH if config.container_type == 'gridfinity' else None,
            'pitch_x_mm': config.pitch_x_mm, 'pitch_y_mm': config.pitch_y_mm,
            'width_mm': config.width_mm, 'depth_mm': config.depth_mm,
            'outer_width_mm': config.width_mm-.5, 'outer_depth_mm': config.depth_mm-.5,
            'height_mm': config.height_mm, 'floor_top_mm': config.floor_top_mm,
            'floor_thickness_mm': config.floor_top_mm-config.foot_height_mm,
            'foot_height_mm': config.foot_height_mm,
            'wall_thickness_mm': config.wall_thickness_mm, 'nozzle_mm': .6,
            'line_width_mm': LINE_WIDTH, 'wall_pattern': config.wall_pattern,
            'wall_perimeters': config.wall_perimeters, 'cell_clearance_mm': .5,
            'container_count': len(config.components), 'cell_count': len(config.cells),
            'components': [{'name': f'bin_{index:02d}', 'cells': [list(cell) for cell in cells]}
                           for index, cells in enumerate(config.components, 1)],
            'construction_frame': 'Planning-grid lower-left XY origin; base bottom Z=0; native bins retain cell registration',
            'stacking_lip': False, 'magnet_holes': False,
            'pattern_note': 'Miura facets and junction webs target the selected wall thickness. Straight divider runs are continuous; folds blend into actual joins.',
            'drawer_floor': config.drawer_floor if config.container_type == 'drawer' else None,
            'fit_note': ('Fits the selected plain drawer floor, with a relieved bottom edge and protected front lock space.'
                         if config.container_type == 'drawer' else 'Nominal Gridfinity feet; check drawer clearance with the interface checker.')
                        + ' Printed fit and stiffness need testing.'}


def bin_catalog():
    drawer_layouts = []
    for family in DRAWER_COLUMNS:
        for depth in range(3,8):
            for height in (1,2):
                for floor in (.8,3.):
                    config = BinConfiguration(family,depth,height,container_type='drawer',drawer_floor=floor)
                    layout = bin_layout(config)
                    drawer_layouts.append({'family':family, 'depth_units':depth, 'height_units':height,
                        **{key:layout[key] for key in ('columns','rows','width_mm','depth_mm',
                            'outer_width_mm','outer_depth_mm','height_mm','pitch_x_mm','pitch_y_mm',
                            'floor_thickness_mm','drawer_floor')}})
    return {'families': [{'id': family, 'columns': columns, 'drawer_columns': DRAWER_COLUMNS[family]}
                         for family, columns in GRID_COLUMNS.items()],
            'container_types': ['gridfinity','drawer'], 'drawer_floors': [.8,3.],
            'drawer_layouts': drawer_layouts,
            'balanced_design': {'wall_pattern':'miura','wall_perimeters':2},
            'depths': list(range(3, 8)), 'heights': [1, 2],
            'wall_patterns': [{'id': 'plain', 'label': 'Plain'}, {'id': 'miura', 'label': 'Miura-ori'}],
            'wall_perimeters': [1, 2], 'defaults': BinConfiguration().as_dict(),
            'dimensions': {'pitch_mm': PITCH, 'wall_line_width_mm': LINE_WIDTH, 'nozzle_mm': .6,
                           'heights_mm': {str(k): v for k, v in HEIGHTS.items()},
                           'foot_height_mm': 4.75, 'floor_top_mm': 7., 'cell_clearance_mm': .5},
            'divider_axes': {'x': 'Vertical edge (x,y) to (x,y+1)',
                             'y': 'Horizontal edge (x,y) to (x+1,y)'},
            'max_cells': 42, 'max_dividers': 71}
