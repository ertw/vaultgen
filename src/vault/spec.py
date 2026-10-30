"""Vault drawer sizes and placements, independent of mating cross-sections.

Dimensions measured from the supplied S/M/L/XL drawer modules are in mm.
Depth grows in 42 mm steps; runner tiers repeat every 48 mm. Increasing a
module's size moves or repeats features rather than scaling their geometry.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType


DEPTH_PITCH = 42.0
TIER_PITCH = 48.0
DRAWER_HEIGHTS = (1, 2, 4)
WALL_PATTERNS = MappingProxyType({'plain': 'Plain', 'waffle': 'Waffle', 'miura': 'Miura-ori'})
PATTERN_CONSTRUCTIONS = MappingProxyType({'recessed': 'Recessed', 'corrugated': 'Two-perimeter corrugated'})
# New user selections favor paired thin walls. Historical data and native
# constructors keep their original defaults so omitted fields retain meaning.
NEW_PATTERN_CONSTRUCTION = 'corrugated'
PATTERN_DEFAULTS = MappingProxyType({
    'wall_pattern': 'plain', 'pattern_pitch': 14.0, 'pattern_depth': 1.7,
    'pattern_line_width': 0.65, 'pattern_faces': 'all', 'pattern_construction': 'recessed',
})
PATTERN_FIELDS = tuple(PATTERN_DEFAULTS)
PATTERN_RANGES = MappingProxyType({
    'pattern_pitch': (8.0, 40.0), 'pattern_depth': (0.2, 2.0),
    'pattern_line_width': (0.6, 1.0),
})
WALL_PERIMETERS = (1, 2, 'full')
NOZZLE_SIZES = (0.6, 0.8)
WALL_FIELDS = ('wall_perimeters', 'nozzle_size', 'wall_pattern', 'pattern_pitch', 'pattern_depth')


def validate_wall_settings(configuration):
    """Resolve the shared panel settings, leaving old saved requests intact."""
    count = getattr(configuration, 'wall_perimeters', None)
    nozzle = getattr(configuration, 'nozzle_size', .6)
    if type(nozzle) not in (int, float) or nozzle not in NOZZLE_SIZES:
        raise ValueError('nozzle_size must be 0.6 or 0.8 mm')
    if count is None:
        if hasattr(configuration, 'nozzle_size'):
            object.__setattr__(configuration, 'nozzle_size', .6)
        return
    if not (type(count) is int and count in (1, 2) or type(count) is str and count == 'full'):
        raise ValueError('wall_perimeters must be 1, 2, or full')
    if configuration.wall_pattern not in ('plain', 'miura'):
        raise ValueError('wall_pattern must be plain or miura')
    for key in ('pattern_pitch', 'pattern_depth'):
        value = getattr(configuration, key)
        low, high = PATTERN_RANGES[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{key} must be a finite number from {low:g} to {high:g} mm')
        object.__setattr__(configuration, key, float(value))
    if count == 'full':
        object.__setattr__(configuration, 'wall_pattern', 'plain')
        object.__setattr__(configuration, 'nozzle_size', .6)
    else:
        object.__setattr__(configuration, 'nozzle_size', float(nozzle))
    if configuration.wall_pattern == 'plain':
        for key in ('pattern_pitch', 'pattern_depth'):
            object.__setattr__(configuration, key, PATTERN_DEFAULTS[key])
    for key, value in (('pattern_faces', 'all'), ('pattern_construction', 'corrugated'),
                       ('pattern_line_width', round(configuration.nozzle_size + .05, 2))):
        if hasattr(configuration, key):
            object.__setattr__(configuration, key, value)


def wall_parameters(configuration):
    return {key: getattr(configuration, key) for key in WALL_FIELDS}


def wall_target_thickness(configuration):
    """Nominal Arachne goal; actual path count still depends on slicer settings."""
    count = getattr(configuration, 'wall_perimeters', None)
    if count == 'full':
        return None
    if count is None:
        return 2 * getattr(configuration, 'pattern_line_width', .65)
    return round(count * (configuration.nozzle_size + .05), 2)


def wall_setting_suffix(configuration):
    if configuration.wall_perimeters == 'full':
        return '_walls_full'
    suffix = f'_{configuration.wall_pattern}_walls_{configuration.wall_perimeters}p_n{configuration.nozzle_size:g}'
    suffix = suffix.replace('.', 'p')
    if configuration.wall_pattern == 'miura' and (configuration.pattern_pitch, configuration.pattern_depth) != (14., 1.7):
        values = (float(configuration.pattern_pitch), float(configuration.pattern_depth))
        suffix += '_' + hashlib.sha256(json.dumps(values).encode()).hexdigest()[:12]
    return suffix


def validate_wall_pattern(configuration):
    """Validate request settings without importing the CAD runtime."""
    validate_wall_settings(configuration)
    if not isinstance(configuration.wall_pattern, str) or configuration.wall_pattern not in WALL_PATTERNS:
        raise ValueError('wall_pattern must be plain, waffle, or miura')
    if not isinstance(configuration.pattern_faces, str) or configuration.pattern_faces not in ('all', 'sides'):
        raise ValueError('pattern_faces must be all or sides')
    if (not isinstance(configuration.pattern_construction, str)
            or configuration.pattern_construction not in PATTERN_CONSTRUCTIONS):
        raise ValueError('pattern_construction must be recessed or corrugated')
    for key, (minimum, maximum) in PATTERN_RANGES.items():
        value = getattr(configuration, key)
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f'{key} must be a finite number from {minimum:g} to {maximum:g} mm')
        object.__setattr__(configuration, key, float(value))
    if (getattr(configuration, 'wall_perimeters', None) is None
            and configuration.pattern_depth + 2 * configuration.pattern_line_width > 3.0 + 1e-9):
        raise ValueError('Pattern depth plus two line widths must fit within the 3 mm wall')


def pattern_parameters(configuration):
    return {key: getattr(configuration, key) for key in PATTERN_FIELDS}


@dataclass(frozen=True)
class FamilyLayout:
    """Outside width and lateral centers of the stacking connector banks."""

    width: float
    bank_centers: tuple[float, ...]


FAMILIES = MappingProxyType({
    "S": FamilyLayout(164.8, (0.0,)),
    "M": FamilyLayout(254.0, (0.0,)),
    "L": FamilyLayout(329.6, (-82.4, 82.4)),
    # The mixed-width XL source really has these unequal bank offsets.
    "XL": FamilyLayout(418.8, (-82.4, 127.0)),
})


@dataclass(frozen=True)
class ModuleSpec:
    """A drawer sleeve size, e.g. ``ModuleSpec('S', 4, 1)`` for S4 1F.

    Supplied references cover depths 3–7 and heights 1, 2, 4 (XL: 1 only).
    Other positive tier counts and deeper boxes are generated extensions,
    not claims of agreement with an unavailable purchased reference.
    ``drawer_columns=2`` selects L²: two S drawers side by side inside the
    standard L envelope. By default each drawer occupies the full module
    height. Add ``drawer_rows=2`` for four S1F drawers in the same L 2F
    module. Rows select drawer contents and placements, not housing geometry.
    """

    family: str = "S"
    depth_units: int = 4
    height_units: int = 1
    module_rear: float = 0.9
    drawer_columns: int = 1
    drawer_rows: int = 1
    wall_pattern: str = 'plain'
    pattern_pitch: float = 14.0
    pattern_depth: float = 1.7
    pattern_line_width: float = 0.65
    pattern_faces: str = 'all'
    pattern_construction: str = 'recessed'
    wall_perimeters: int | str | None = None
    nozzle_size: float = 0.6

    def __post_init__(self):
        validate_wall_pattern(self)
        if self.wall_pattern == 'plain' and self.wall_perimeters is None:
            # Unused controls must not create competing cache identities for
            # the unchanged plain module.
            for key, value in PATTERN_DEFAULTS.items():
                object.__setattr__(self, key, value)
        if type(self.module_rear) not in (int, float) or self.module_rear not in (0.9, 2.0):
            raise ValueError('Module rear must be 0.9 or 2.0 mm')
        if self.family not in FAMILIES:
            raise ValueError(f"Unknown Vault family {self.family!r}; choose {', '.join(FAMILIES)}")
        if type(self.depth_units) is not int or self.depth_units < 3:
            raise ValueError("depth_units must be an integer of at least 3 so the connectors fit")
        if type(self.height_units) is not int or self.height_units < 1:
            raise ValueError("height_units must be a positive integer")
        if type(self.drawer_columns) is not int or self.drawer_columns not in (1, 2):
            raise ValueError('drawer_columns must be 1 or 2')
        if self.drawer_columns == 2 and self.family != 'L':
            raise ValueError('Two drawer columns require family L (L², two S drawers)')
        if type(self.drawer_rows) is not int or self.drawer_rows not in (1, 2):
            raise ValueError('drawer_rows must be 1 or 2')
        if self.drawer_rows == 2 and (self.family != 'L' or self.height_units != 2 or self.drawer_columns != 2):
            raise ValueError('Two drawer rows require an L 2F module with two columns')

    @property
    def layout(self) -> FamilyLayout:
        return FAMILIES[self.family]

    @property
    def width(self) -> float:
        return self.layout.width

    @property
    def half_width(self) -> float:
        return self.width / 2

    @property
    def depth(self) -> float:
        return DEPTH_PITCH * self.depth_units + 20.1

    @property
    def height(self) -> float:
        """Distance between the outside skins, excluding stacking connectors."""
        return TIER_PITCH * self.height_units - 1.0

    @property
    def bank_centers(self) -> tuple[float, ...]:
        return self.layout.bank_centers

    @property
    def tier_offsets(self) -> tuple[float, ...]:
        return tuple(TIER_PITCH * index for index in range(self.height_units))

    @property
    def drawer_family(self) -> str:
        """Family of each drawer; L² houses two S drawers in an L envelope."""
        return 'S' if self.drawer_columns == 2 else self.family

    @property
    def drawer_centers(self) -> tuple[float, ...]:
        return (-82.4, 82.4) if self.drawer_columns == 2 else (0.0,)

    @property
    def drawer_height_units(self) -> int:
        return self.height_units // self.drawer_rows

    @property
    def drawer_origins(self) -> tuple[tuple[float, float], ...]:
        """(X, Z) origins of the drawers within the module's native frame."""
        return tuple((x, row * self.drawer_height_units * TIER_PITCH)
                     for row in range(self.drawer_rows) for x in self.drawer_centers)

    @property
    def name(self) -> str:
        columns = '²' if self.drawer_columns == 2 else ''
        pattern = f' · {WALL_PATTERNS[self.wall_pattern]}' if self.wall_pattern != 'plain' else ''
        if pattern and self.pattern_construction == 'corrugated':
            pattern += ' corrugated'
        if self.wall_perimeters is not None:
            pattern += (' · Full width' if self.wall_perimeters == 'full' else
                        f' · {self.wall_perimeters} perimeter{ "s" if self.wall_perimeters == 2 else ""}, {self.nozzle_size:g} mm nozzle')
        return f"{self.family}{self.depth_units}{columns} Module {self.height_units}F" + (" · 2 mm rear" if self.module_rear == 2 else "") + pattern

    @property
    def pattern_suffix(self) -> str:
        if self.wall_perimeters is not None:
            return wall_setting_suffix(self)
        if self.wall_pattern == 'plain':
            return ''
        values = pattern_parameters(self)
        # Construction has its own readable suffix, preserving existing
        # recessed aliases, including their nondefault-parameter digests.
        values.pop('pattern_construction')
        custom = any(values[key] != value for key, value in PATTERN_DEFAULTS.items()
                     if key not in ('wall_pattern', 'pattern_construction'))
        digest = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:12]
        construction = '_corrugated' if self.pattern_construction == 'corrugated' else ''
        return f'_{self.wall_pattern}{construction}' + (f'_{digest}' if custom else '')

    @property
    def slug(self) -> str:
        columns = '_2_columns' if self.drawer_columns == 2 else ''
        return f"{self.family.lower()}{self.depth_units}{columns}_module_{self.height_units}f" + ("_rear_2mm" if self.module_rear == 2 else "") + self.pattern_suffix


DEFAULT_SPEC = ModuleSpec()
