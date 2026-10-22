"""Matching peripheral rebates; inner lands retain the original seating datum."""
from dataclasses import dataclass
from math import isfinite
from build123d import Face, Solid, Plane
from .envelope import _smooth_sleeve, EnvelopeDimensions
from .spec import DEFAULT_SPEC

@dataclass(frozen=True)
class ShadowGap:
    depth: float = 0.5
    width: float = 1.0

    def __post_init__(self):
        if not all(isfinite(v) and v > 0 for v in (self.depth, self.width)):
            raise ValueError('Shadow gap dimensions must be finite and positive')
        if self.depth > 1 or self.width > 1.5:
            raise ValueError('Rebate exceeds the supported seating-land allowance')

DEFAULT_GAP = ShadowGap()

def perimeter_rebate(part, y, direction, spec=DEFAULT_SPEC, gap=DEFAULT_GAP):
    """Remove only a strip along the outside silhouette, away from runners."""
    sleeve = _smooth_sleeve(spec, EnvelopeDimensions())
    face = min(sleeve.faces(), key=lambda f: f.center().Y)
    wire = face.outer_wire()
    inner = wire.offset_2d(-gap.width)
    # The profile's wire orientation determines offset sign. Require inset.
    if Face(inner).area > face.area:
        inner = wire.offset_2d(gap.width)
    ring = Face(wire, [inner])
    cutter = Solid.extrude(ring, (0, direction*(gap.depth + .002), 0))
    cutter = cutter.translate((0, y - direction*.001, 0))
    return part.cut(cutter)
