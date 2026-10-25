"""Vault drawer sizes and placements, independent of mating cross-sections.

Dimensions measured from the supplied S/M/L/XL drawer modules are in mm.
Depth grows in 42 mm steps; runner tiers repeat every 48 mm. Increasing a
module's size moves or repeats features rather than scaling their geometry.
"""
from dataclasses import dataclass
from types import MappingProxyType


DEPTH_PITCH = 42.0
TIER_PITCH = 48.0


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
    """

    family: str = "S"
    depth_units: int = 4
    height_units: int = 1
    module_rear: float = 0.9

    def __post_init__(self):
        if type(self.module_rear) not in (int, float) or self.module_rear not in (0.9, 2.0):
            raise ValueError('Module rear must be 0.9 or 2.0 mm')
        if self.family not in FAMILIES:
            raise ValueError(f"Unknown Vault family {self.family!r}; choose {', '.join(FAMILIES)}")
        if type(self.depth_units) is not int or self.depth_units < 3:
            raise ValueError("depth_units must be an integer of at least 3 so the connectors fit")
        if type(self.height_units) is not int or self.height_units < 1:
            raise ValueError("height_units must be a positive integer")

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
    def name(self) -> str:
        return f"{self.family}{self.depth_units} Module {self.height_units}F" + (" · 2 mm rear" if self.module_rear == 2 else "")

    @property
    def slug(self) -> str:
        return f"{self.family.lower()}{self.depth_units}_module_{self.height_units}f" + ("_rear_2mm" if self.module_rear == 2 else "")


DEFAULT_SPEC = ModuleSpec()
