"""Native two-perimeter reliefs in the drawer's nonmating rear wall.

Both faces are relieved inside the original 3 mm skin. The box floor fillet,
rounded rear corners, top rim and all front/runner interfaces retain solid
lands. Pattern definitions and normal offsets are shared with module walls;
module pattern selections and parameters do not configure this rear panel.
"""
from dataclasses import dataclass
from types import SimpleNamespace

from .drawer import DrawerLayout
from .wall_patterns import (
    PatternPanel, _corrugated_inner_cutters, _miura_cutters, _waffle_cutters,
    corrugated_miura_spec,
)


BOX_REAR_PATTERN_PITCH = 14.0
BOX_REAR_PATTERN_DEPTH = 1.7
BOX_REAR_PATTERN_LINE_WIDTH = .65
BOX_REAR_WALL = 3.0
REAR_LAND = 3.0


@dataclass(frozen=True)
class RearPatternPanel(PatternPanel):
    """Registered box frame: horizontal X, vertical Z, inward positive Y."""

    def point(self, u, v, depth):
        return (u, self.datum + self.origin_depth + self.direction * depth, v)


@dataclass(frozen=True)
class _RearPatternParameters:
    wall_pattern: str
    pattern_pitch: float = BOX_REAR_PATTERN_PITCH
    pattern_depth: float = BOX_REAR_PATTERN_DEPTH
    pattern_line_width: float = BOX_REAR_PATTERN_LINE_WIDTH


def rear_pattern_panel(spec):
    """Flat rear skin excluding the cavity corner, floor fillet and top rim.

    The rear cavity's straight segment ends at X=±(60.1+width_delta).
    The 1 mm floor fillet ends one millimeter above the selected floor or the
    retained 0.8 mm rim foundation of a floorless Gridfinity box. An additional
    3 mm solid land protects both, and the top rim keeps 3 mm.
    Gridfinity sockets start beyond Y=7.7, outside the rear wall at Y=2.3–5.3.
    """
    layout = DrawerLayout(spec)
    half_width = 60.1 + layout.width_delta - REAR_LAND
    bottom = 5.0 + max(.8, getattr(spec, 'box_floor', .8)) + 1.0 + REAR_LAND
    top = 42.5 + layout.height_delta - REAR_LAND
    return RearPatternPanel('rear', 2.3, (-half_width, bottom, half_width, top))


def box_rear_pattern_cutters(spec):
    """Return native outside and normally offset inside relief cutters."""
    style = getattr(spec, 'box_rear_pattern', 'plain')
    if not isinstance(style, str) or style not in ('plain', 'waffle', 'miura'):
        raise ValueError('Box rear pattern must be plain, waffle, or miura')
    if style == 'plain':
        return []
    panel = rear_pattern_panel(spec)
    parameters = _RearPatternParameters(style)
    if style == 'miura':
        parameters = corrugated_miura_spec(parameters, BOX_REAR_WALL)
    outside = list(_waffle_cutters(panel, parameters) if style == 'waffle'
                   else _miura_cutters(panel, parameters))
    if not outside:
        raise ValueError('Rear pattern does not fit the protected wall panel')
    inside = _corrugated_inner_cutters(
        panel, parameters, SimpleNamespace(channel_outer_inset=BOX_REAR_WALL), outside)
    return [*outside, *inside]


def apply_box_rear_pattern(part, spec):
    """Apply the selected rear pattern to an already registered native box."""
    cutters = box_rear_pattern_cutters(spec)
    if not cutters:
        return part
    result = part.cut(*cutters).clean()
    if not result.is_valid or len(result.solids()) != 1 or len(result.shells()) != 1:
        raise ValueError('Expected one valid box solid after rear wall patterning')
    return result
