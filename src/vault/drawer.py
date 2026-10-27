"""Shared box/facade mating datums, independent of decorative surfaces.

Family widths and 42/48 mm pitches come from ModuleSpec. Measurements of the
S/M/L 1F and 2F sources place the box 5 mm above the sleeve datum, with a
2.3 mm rear inset and a 15.3 mm inset on each side. The lock stays at the
bottom tier; the tall trays repeat their runner channels and outer screws.
"""
from dataclasses import dataclass
from .spec import DEFAULT_SPEC, ModuleSpec


def drawer_spec(spec=DEFAULT_SPEC):
    """Normalize public part specs while limiting supported printable families."""
    normalized = ModuleSpec(getattr(spec, 'drawer_family', spec.family),
                            getattr(spec, "depth_units", 4),
                            getattr(spec, 'drawer_height_units', spec.height_units))
    if normalized.family not in ("S", "M", "L"):
        raise ValueError("Drawer parts support S, M, and L families")
    if normalized.height_units not in (1, 2):
        raise ValueError("Drawer parts support 1F and 2F heights")
    return normalized


@dataclass(frozen=True)
class DrawerLayout:
    spec: ModuleSpec = DEFAULT_SPEC

    def __post_init__(self):
        object.__setattr__(self, "spec", drawer_spec(self.spec))

    @property
    def half_width(self):
        return self.spec.half_width - 15.3

    @property
    def width_delta(self):
        return (self.spec.width - DEFAULT_SPEC.width) / 2

    @property
    def depth_delta(self):
        return self.spec.depth - DEFAULT_SPEC.depth

    @property
    def height_delta(self):
        return self.spec.height - DEFAULT_SPEC.height

    @property
    def screw_positions(self):
        """(X,Z) centers shared by the box and its facade in assembly space."""
        outer = {"S": 51.45, "M": 92.45, "L": 130.25}[self.spec.family]
        positions = [(side * outer, 23.5 + tier)
                     for tier in self.spec.tier_offsets for side in (-1, 1)]
        if self.spec.family != "S":
            positions.extend((side * 51.45, 23.5) for side in (-1, 1))
        return tuple(positions)
