"""Assembly invariants across all supported sizes without importing CAD."""
from itertools import product
import unittest

from vault.assembly import assembly_definition, transform_point
from vault.generator import Configuration


class AssemblyDefinitionTests(unittest.TestCase):
    def test_all_configurations_have_complete_rigid_instances(self):
        for family, depth, height, floor, rear in product('SML', range(3, 8), (1, 2), (.8, 3.), (.9, 2.)):
            configuration = Configuration(family, depth, height, 'set', floor, rear)
            scene = assembly_definition(configuration)
            instances = scene['instances']
            with self.subTest(configuration=configuration):
                self.assertEqual(len(instances), 5 + 4 * height)
                self.assertEqual(len({item['id'] for item in instances}), len(instances))
                self.assertEqual({item['kind'] for item in instances}, set(configuration.parts))
                for item in instances:
                    matrix = item['transform']
                    self.assertEqual(len(matrix), 16)
                    self.assertEqual(matrix[3::4], [0., 0., 0., 1.])
                    axes = [matrix[start:start + 3] for start in (0, 4, 8)]
                    for i, j in product(range(3), repeat=2):
                        self.assertAlmostEqual(sum(a * b for a, b in zip(axes[i], axes[j])), float(i == j))
                    a, b, c = axes
                    determinant = (a[0] * (b[1] * c[2] - b[2] * c[1])
                                   - a[1] * (b[0] * c[2] - b[2] * c[0])
                                   + a[2] * (b[0] * c[1] - b[1] * c[0]))
                    self.assertAlmostEqual(determinant, 1.)

    def test_runner_guide_and_slide_share_seated_datums(self):
        for family, depth, height in product('SML', range(3, 8), (1, 2)):
            instances = assembly_definition(Configuration(family, depth, height))['instances']
            for guide in (item for item in instances if item['kind'] == 'runner_guides'):
                slide = next(item for item in instances if item['kind'] == 'runner_slides'
                             and item['side'] == guide['side'] and item['tier'] == guide['tier'])
                # The measured slide seating origin is (13.5,25.8,4.8) in a
                # guide's native frame. Compare their placed axes as well.
                for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
                    expected = transform_point(guide['transform'], tuple(a + b for a, b in zip(point, (13.5, 25.8, 4.8))))
                    actual = transform_point(slide['transform'], point)
                    for a, b in zip(actual, expected):
                        self.assertAlmostEqual(a, b)

    def test_depth_moves_facade_and_gears_but_height_does_not_repeat_gears(self):
        for depth, height in product(range(3, 8), (1, 2)):
            instances = assembly_definition(Configuration('L', depth, height))['instances']
            facade = next(item for item in instances if item['kind'] == 'facade')
            self.assertAlmostEqual(facade['transform'][13], depth * 42 + 20.1)
            rails = [item for item in instances if item['kind'] == 'rails']
            self.assertEqual(len(rails), 2)
            self.assertEqual({item['component'] for item in rails}, {'plain', 'retained'})
            for rail in rails:
                self.assertAlmostEqual(rail['transform'][13], depth * 42 + 15.1)

    def test_selection_does_not_remove_assembly_instances(self):
        complete = assembly_definition(Configuration())['instances']
        selected = assembly_definition(Configuration(part='rails'))['instances']
        self.assertEqual(complete, selected)

    def test_drawer_explosion_keeps_attached_parts_forward_of_shell(self):
        for depth in range(3, 8):
            instances = assembly_definition(Configuration('S', depth, 2))['instances']
            for item in instances:
                self.assertEqual(item['group'], item['parent'])
                if item['group'] == 'drawer':
                    self.assertGreaterEqual(item['explode'][1], (depth * 42 + 20.1) * .8)
                else:
                    self.assertEqual(item['explode'][1], 0)


if __name__ == '__main__':
    unittest.main()
