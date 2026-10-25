"""Check both configured thicknesses on actual native solids."""
import unittest
from build123d import Vector
from vault.box import BoxSpec, build_box
from vault.model import build_module
from vault.spec import ModuleSpec


class ThicknessTests(unittest.TestCase):
    def test_native_thicknesses(self):
        for kind, values in [('box', (0.8, 3.0)), ('module', (0.9, 2.0))]:
            for value in values:
                with self.subTest(kind=kind, thickness=value):
                    spec = BoxSpec(box_floor=value) if kind == 'box' else ModuleSpec(module_rear=value)
                    shape = build_box(spec=spec) if kind == 'box' else build_module(spec=spec)
                    self.assertTrue(shape.is_valid)
                    self.assertEqual(len(shape.solids()), 1)
                    inside = Vector(0, 80, 5+value-.1) if kind == 'box' else Vector(35, value-.1, 23)
                    outside = Vector(0, 80, 5+value+.1) if kind == 'box' else Vector(35, value+.1, 23)
                    self.assertTrue(shape.is_inside(inside))
                    self.assertFalse(shape.is_inside(outside))
