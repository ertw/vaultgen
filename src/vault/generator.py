"""Bounded generator requests shared by HTTP and the isolated CAD worker."""
from dataclasses import dataclass, asdict

from .spec import FAMILIES

PARTS = {'set': 'Complete set', 'module': 'Module', 'box': 'Box',
         'facade': 'Facade', 'rails': 'Geared rails'}


@dataclass(frozen=True)
class Configuration:
    family: str = 'S'
    depth_units: int = 4
    height_units: int = 1
    part: str = 'set'

    def __post_init__(self):
        if self.family not in ('S', 'M', 'L'):
            raise ValueError('Choose family S, M, or L')
        if type(self.depth_units) is not int or self.depth_units not in range(3, 8):
            raise ValueError('Depth must be an integer from 3 to 7')
        if type(self.height_units) is not int or self.height_units not in (1, 2):
            raise ValueError('Height must be 1F or 2F; L × 2F is the maximum size')
        if self.part not in PARTS:
            raise ValueError('Choose a module, box, facade, rails, or complete set')

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
    def parts(self):
        return ('module', 'box', 'facade', 'rails') if self.part == 'set' else (self.part,)


def catalog():
    return {'families': [{'id': key, 'width_mm': FAMILIES[key].width}
                         for key in ('S', 'M', 'L')],
            'depths': list(range(3, 8)), 'heights': [1, 2],
            'parts': [{'id': key, 'name': value} for key, value in PARTS.items()],
            'defaults': Configuration().as_dict()}
