"""Reproduce the shared native/SVG font outlines from the pinned Matplotlib font.

Run in the prepared environment. The generated JSON, including the font license
and source checksum, is the only font input used by the application or CAD.
"""
import hashlib
import json
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from matplotlib import get_data_path


class OutlinePen(BasePen):
    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.commands = []

    def _moveTo(self, p): self.commands.append(['M', *p])
    def _lineTo(self, p): self.commands.append(['L', *p])
    def _qCurveToOne(self, p1, p2): self.commands.append(['Q', *p1, *p2])
    def _curveToOne(self, p1, p2, p3): self.commands.append(['C', *p1, *p2, *p3])
    def _closePath(self): self.commands.append(['Z'])


def main():
    source = Path(get_data_path()) / 'fonts/ttf/DejaVuSans-Bold.ttf'
    font = TTFont(source)
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    characters = list(range(32, 127)) + list(range(160, 256)) + [0x2013, 0x2014, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x20ac]
    records = {}
    for codepoint in characters:
        if codepoint not in cmap:
            continue
        glyph = glyphs[cmap[codepoint]]
        pen, bounds = OutlinePen(glyphs), BoundsPen(glyphs)
        glyph.draw(pen)
        glyph.draw(bounds)
        records[chr(codepoint)] = {'advance': glyph.width,
                                   'bounds': list(bounds.bounds) if bounds.bounds else None,
                                   'commands': pen.commands}
    data = {'schema': 'vault-label-font/v1', 'family': 'DejaVu Sans Bold',
            'units_per_em': font['head'].unitsPerEm,
            'ascent': font['hhea'].ascent, 'descent': font['hhea'].descent,
            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'license': (source.parent / 'LICENSE_DEJAVU').read_text(),
            'glyphs': records}
    target = Path(__file__).resolve().parents[1] / 'src/vault/static/label-font.json'
    target.write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False) + '\n')
    print(f'{target}: {len(records)} glyphs, {target.stat().st_size} bytes')


if __name__ == '__main__':
    main()
