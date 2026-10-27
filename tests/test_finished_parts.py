"""Finished assembly solids omit removable supports while preserving fit datums."""
import unittest

from vault.assembly import apply_transform, rigid_transform
from vault.box import BoxSpec, build_box
from vault.model import build_module
from vault.shell import POCKET_LEDGE_HEIGHT, ShellDimensions
from vault.spec import ModuleSpec


class FinishedPartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module_spec = ModuleSpec('S', 3, 2, module_rear=2.)
        cls.module = build_module(spec=cls.module_spec)
        cls.finished_module = build_module(spec=cls.module_spec, include_supports=False)
        box_spec = BoxSpec('S', 3, 2, box_floor=3.)
        cls.box = build_box(spec=box_spec)
        cls.finished_box = build_box(spec=box_spec, include_supports=False)

    def test_support_removal_preserves_valid_solid_and_external_datums(self):
        for printable, finished in ((self.module, self.finished_module), (self.box, self.finished_box)):
            self.assertTrue(finished.is_valid)
            self.assertEqual(len(finished.solids()), 1)
            self.assertEqual(len(finished.shells()), 1)
            self.assertGreater(printable.volume, finished.volume)
            before, after = printable.bounding_box(), finished.bounding_box()
            for a, b in zip((*before.min, *before.max), (*after.min, *after.max)):
                self.assertAlmostEqual(a, b, places=5)

    def test_module_omits_both_webs_on_each_tier(self):
        d, spec = ShellDimensions(), self.module_spec
        y = spec.depth - d.pocket_front_offset - d.pocket_length + 2
        z = d.pocket_floor + POCKET_LEDGE_HEIGHT - .15 - d.pocket_support_thickness / 2
        for tier in spec.tier_offsets:
            for point in ((-72, y, z + tier), (72, y, 47 - z + tier)):
                self.assertTrue(self.module.is_inside(point))
                self.assertFalse(self.finished_module.is_inside(point))

    def test_box_omits_both_sheets_on_each_tier(self):
        for tier in self.module_spec.tier_offsets:
            for side in (-1, 1):
                point = (side * 66.15, 36, 23.5 + tier)
                self.assertTrue(self.box.is_inside(point))
                self.assertFalse(self.finished_box.is_inside(point))
                # The backing wall stays intact behind the open runner slot.
                self.assertTrue(self.finished_box.is_inside((side * 64, 36, 23.5 + tier)))

    def test_finished_shapes_retain_configured_original_thicknesses(self):
        for state, module, box in (('printable', self.module, self.box),
                                   ('finished', self.finished_module, self.finished_box)):
            with self.subTest(state=state):
                self.assertTrue(module.is_inside((0, 1.9, 23.5)))
                self.assertFalse(module.is_inside((0, 2.1, 23.5)))
                self.assertTrue(box.is_inside((0, 60, 7.9)))
                self.assertFalse(box.is_inside((0, 60, 8.1)))

    def test_cad_transform_uses_the_same_column_major_coordinates_as_viewer(self):
        from build123d import Solid
        original = Solid.make_box(1, 2, 3)
        placed = apply_transform(original, rigid_transform(((0, 0, -1), (0, 1, 0), (1, 0, 0)),
                                                           (10, 20, 30)))
        for actual, expected in zip(placed.bounding_box().min, (7, 20, 30)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(placed.bounding_box().max, (10, 22, 31)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(placed.volume, original.volume)


if __name__ == '__main__':
    unittest.main()
