"""Bounded label requests and exact shared-font layout, without CAD imports."""
from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

from .spec import FAMILIES


DIMENSIONS = {
    'width_mm': 47., 'height_mm': 19.4, 'thickness_mm': 2.,
    'corner_radius_mm': .8, 'rounded_end_radius_mm': 9.7, 'outline': 'd-profile-right', 'face_thickness_mm': .9,
    'rim_thickness_mm': .8, 'inlay_depth_mm': .6,
    'safe_margin_mm': 3., 'line_gap_mm': 1.5,
}
MAX_CHARACTERS_PER_LINE = 96
FONT_PATH = Path(__file__).with_name('static') / 'label-font.json'


def label_dimensions(family='S'):
    """Lengthen only the straight section to match the selected facade width."""
    family = getattr(family, 'family', family)
    if family not in ('S', 'M', 'L'):
        raise ValueError('Choose label family S, M, or L')
    width = DIMENSIONS['width_mm'] + (FAMILIES[family].width-FAMILIES['S'].width)/2
    return {**DIMENSIONS, 'width_mm': round(width, 6)}


def label_outline_svg(family='S'):
    dimensions = label_dimensions(family)
    width, height = dimensions['width_mm'], dimensions['height_mm']
    radius, corner = dimensions['rounded_end_radius_mm'], dimensions['corner_radius_mm']
    return (f'M{corner:g} 0 H{width-radius:g} A{radius:g} {radius:g} 0 0 1 {width-radius:g} {height:g} '
            f'H{corner:g} A{corner:g} {corner:g} 0 0 1 0 {height-corner:g} '
            f'V{corner:g} A{corner:g} {corner:g} 0 0 1 {corner:g} 0 Z')


@lru_cache(maxsize=1)
def label_font():
    return json.loads(FONT_PATH.read_text())


def _color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Colors must use six-digit hex notation, such as #ffffff')
    return value.lower()


@dataclass(frozen=True)
class LabelLine:
    text: str = 'BOLTS'
    size: float = 6.
    color: str = '#ffffff'

    def __post_init__(self):
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > MAX_CHARACTERS_PER_LINE:
            raise ValueError(f'Each label line needs 1–{MAX_CHARACTERS_PER_LINE} characters, including visible text')
        if any(char not in label_font()['glyphs'] for char in self.text):
            raise ValueError('Use supported Latin letters, numbers, spaces, and punctuation')
        if type(self.size) not in (float, int) or not 3 <= self.size <= 10 or not math.isfinite(self.size):
            raise ValueError('Font size must be between 3 and 10 mm')
        object.__setattr__(self, 'size', float(self.size))
        object.__setattr__(self, 'color', _color(self.color))


@dataclass(frozen=True)
class LabelConfiguration:
    lines: tuple[LabelLine, ...] = (LabelLine(),)
    background: str = '#30343b'
    hollow: bool = True
    part: str = 'label'
    family: str = 'S'

    def __post_init__(self):
        if self.part != 'label':
            raise ValueError('Expected a label configuration')
        if not isinstance(self.family, str):
            raise ValueError('Choose label family S, M, or L')
        label_dimensions(self.family)
        if type(self.hollow) is not bool:
            raise ValueError('Hollow must be true or false')
        if not isinstance(self.lines, (list, tuple)) or not 1 <= len(self.lines) <= 2:
            raise ValueError('Choose one or two label lines')
        converted = []
        for line in self.lines:
            if isinstance(line, dict) and not set(line) - {'text', 'size', 'color'}:
                try:
                    line = LabelLine(**line)
                except TypeError as error:
                    raise ValueError('Invalid label line') from error
            if not isinstance(line, LabelLine):
                raise ValueError('Each line needs text, size and color without unknown fields')
            converted.append(line)
        object.__setattr__(self, 'lines', tuple(converted))
        object.__setattr__(self, 'background', _color(self.background))
        if len({self.background, *(line.color for line in self.lines)}) < 2:
            raise ValueError('Choose at least two different colors for the label')
        if any(line.color == self.background for line in self.lines):
            raise ValueError('Each text color must differ from the background color')
        label_layout(self)

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError('Expected a label configuration with no unknown fields')
        try:
            return cls(**value)
        except TypeError as error:
            raise ValueError('Invalid label configuration') from error

    def as_dict(self):
        return {'part': self.part, 'family': self.family, 'background': self.background, 'hollow': self.hollow,
                'lines': [asdict(line) for line in self.lines]}

    @property
    def parts(self):
        return ('label',)

    @property
    def key(self):
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True).encode()).hexdigest()

    @property
    def slug(self):
        return f'{self.key[:16]}_label'

    @property
    def name(self):
        return f'{self.family} Label · ' + ' / '.join(line.text for line in self.lines)


def label_layout(config):
    """Center visible ink bounds, with 1.5 mm between one/two lines.

    Glyph coordinates and baselines use a bottom-left, Y-up face coordinate
    system. Spaces advance the pen but don't affect the visible bounds.
    """
    font, dimensions = label_font(), label_dimensions(config)
    lines = []
    for line in config.lines:
        scale, cursor, bounds, glyphs = line.size / font['units_per_em'], 0., [], []
        for char in line.text:
            glyph = font['glyphs'][char]
            glyphs.append({'character': char, 'x': cursor})
            if glyph['bounds'] is not None:
                x0, y0, x1, y1 = glyph['bounds']
                bounds.append((cursor+x0*scale, y0*scale, cursor+x1*scale, y1*scale))
            cursor += glyph['advance']*scale
        if not bounds:
            raise ValueError('Each line needs visible text')
        ink = [min(b[0] for b in bounds), min(b[1] for b in bounds),
               max(b[2] for b in bounds), max(b[3] for b in bounds)]
        if ink[2] - ink[0] > dimensions['width_mm'] - 2*dimensions['safe_margin_mm']:
            raise ValueError('Text is too wide; shorten it or reduce the font size')
        offset = (dimensions['width_mm']-ink[2]-ink[0])/2
        lines.append({'text': line.text, 'color': line.color, 'size': line.size,
                      'scale': scale, 'x': offset, 'bounds': ink,
                      'glyphs': [{**g, 'x': g['x']+offset} for g in glyphs]})
    height = sum(line['bounds'][3]-line['bounds'][1] for line in lines)
    height += dimensions['line_gap_mm']*(len(lines)-1)
    if height > dimensions['height_mm'] - 2*dimensions['safe_margin_mm']:
        raise ValueError('Text is too tall; reduce one or both font sizes')
    top = (dimensions['height_mm']+height)/2
    for line in lines:
        ink = line['bounds']
        line['baseline_y'] = top-ink[3]
        top -= ink[3]-ink[1]+dimensions['line_gap_mm']
    return lines


def label_catalog():
    return {'dimensions': label_dimensions(), 'font': label_font()['family'],
            'outline_svg': label_outline_svg(),
            'families': [{'id': family, 'dimensions': label_dimensions(family),
                          'outline_svg': label_outline_svg(family)} for family in ('S','M','L')],
            'font_url': '/static/label-font.json', 'defaults': LabelConfiguration().as_dict(),
            'font_size_min_mm': 3, 'font_size_max_mm': 10, 'max_characters_per_line': MAX_CHARACTERS_PER_LINE,
            'max_lines': 2}
