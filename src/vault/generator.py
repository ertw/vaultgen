"""Bounded generator requests shared by HTTP and the isolated CAD worker."""
from dataclasses import dataclass, asdict

from .spec import FAMILIES, PATTERN_CONSTRUCTIONS, PATTERN_DEFAULTS, PATTERN_RANGES, WALL_PATTERNS, validate_wall_pattern

# Keep request validation independent of the CAD runtime.
ACCESSORY_PARTS = ('key', 'spring', 'runner_stop', 'facade_cap', 'key_cap', 'latch')
ASSEMBLY_PARTS = ('module', 'box', 'facade', 'rails', 'runner_guides', 'runner_slides')

PARTS = {'set': 'Complete set', 'module': 'Module', 'box': 'Box',
         'facade': 'Facade', 'rails': 'Geared rails',
         'runner_guides': 'Runner guides', 'runner_slides': 'Runner slides',
         'key': 'Key', 'spring': 'Spring', 'runner_stop': 'Runner stop',
         'facade_cap': 'Facade cap', 'key_cap': 'Key cap', 'latch': 'Latch'}


@dataclass(frozen=True)
class Configuration:
    family: str = 'S'
    depth_units: int = 4
    height_units: int = 1
    part: str = 'set'
    box_floor: float = 0.8
    module_rear: float = 0.9
    drawer_columns: int = 1
    drawer_rows: int = 1
    wall_pattern: str = 'plain'
    pattern_pitch: float = 14.0
    pattern_depth: float = 1.7
    pattern_line_width: float = 0.65
    pattern_faces: str = 'all'
    pattern_construction: str = 'recessed'

    def __post_init__(self):
        validate_wall_pattern(self)
        for key, choices in (('box_floor', (0.8, 3.0)), ('module_rear', (0.9, 2.0))):
            value = getattr(self, key)
            if type(value) not in (int, float) or value not in choices:
                raise ValueError(f'{key} must be one of {choices} mm')
        if self.family not in ('S', 'M', 'L'):
            raise ValueError('Choose family S, M, or L')
        if type(self.drawer_columns) is not int or self.drawer_columns not in (1, 2):
            raise ValueError('Drawer columns must be 1 or 2')
        if self.drawer_columns == 2 and self.family != 'L':
            raise ValueError('Two drawer columns require family L')
        if type(self.depth_units) is not int or self.depth_units not in range(3, 8):
            raise ValueError('Depth must be an integer from 3 to 7')
        if type(self.height_units) is not int or self.height_units not in (1, 2):
            raise ValueError('Height must be 1F or 2F; L × 2F is the maximum size')
        if type(self.drawer_rows) is not int or self.drawer_rows not in (1, 2):
            raise ValueError('Drawer rows must be 1 or 2')
        if self.drawer_rows == 2 and (self.family, self.height_units, self.drawer_columns) != ('L', 2, 2):
            raise ValueError('Two drawer rows require an L 2F module with two columns')
        if self.part not in PARTS:
            raise ValueError('Choose a supported part or complete set')

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError('Expected a size configuration with no unknown fields')
        try:
            return cls(**value)
        except TypeError as error:
            raise ValueError('Invalid size configuration') from error

    def as_dict(self):
        return asdict(self)

    @property
    def drawer_family(self):
        return 'S' if self.drawer_columns == 2 else self.family

    @property
    def drawer_height_units(self):
        return self.height_units // self.drawer_rows

    @property
    def drawer_count(self):
        return self.drawer_columns * self.drawer_rows

    @property
    def print_copies(self):
        """Copies of each exported STL needed for the selected drawer assembly.

        Paired files already contain one side each. Universal accessory files
        contain one part, so stop and facade-cap counts include both sides.
        """
        count, height = self.drawer_count, self.drawer_height_units
        screws = 2 * height if self.drawer_family == 'S' else 2 + 2 * height
        return {
            'module': 1, 'box': count, 'facade': count, 'rails': count,
            'runner_guides': count * height, 'runner_slides': count * height,
            'key': count, 'spring': count, 'latch': count,
            'runner_stop': 2 * count * height,
            'facade_cap': screws * count, 'key_cap': count,
        }

    @property
    def parts(self):
        return tuple(key for key in PARTS if key != 'set') if self.part == 'set' else (self.part,)


def catalog():
    return {'families': [{'id': key, 'width_mm': FAMILIES[key].width}
                         for key in ('S', 'M', 'L')],
            'depths': list(range(3, 8)), 'heights': [1, 2],
            'drawer_layouts': [
                {'columns': 1, 'rows': 1, 'name': 'One drawer', 'families': ['S', 'M', 'L']},
                {'columns': 2, 'rows': 1, 'name': 'Two drawers', 'families': ['L'], 'drawer_family': 'S'},
                {'columns': 2, 'rows': 2, 'name': 'Four drawers', 'families': ['L'],
                 'heights': [2], 'drawer_family': 'S'},
            ],
            'parts': [{'id': key, 'name': value, 'common': key in ACCESSORY_PARTS} for key, value in PARTS.items()],
            'thicknesses': {'box_floor': [0.8, 3.0], 'module_rear': [0.9, 2.0]},
            'wall_patterns': [{'id': key, 'name': value} for key, value in WALL_PATTERNS.items()],
            'pattern_constructions': [{'id': key, 'name': value} for key, value in PATTERN_CONSTRUCTIONS.items()],
            'pattern_faces': [{'id': 'all', 'name': 'All four long faces'},
                              {'id': 'sides', 'name': 'Left and right sides'}],
            'pattern_settings': {
                **{key.removeprefix('pattern_'): {'min': bounds[0], 'max': bounds[1],
                                                'default': PATTERN_DEFAULTS[key]}
                   for key, bounds in PATTERN_RANGES.items()},
                'wall_thickness': 3.0,
            },
            'defaults': Configuration().as_dict()}


def parse_configuration(value):
    """Dispatch independent label jobs without changing complete drawer sets."""
    if isinstance(value, dict) and value.get('part') == 'label':
        from .label_config import LabelConfiguration
        return LabelConfiguration.parse(value)
    return Configuration.parse(value)
