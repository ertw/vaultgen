"""Assembly invariants across all supported sizes without importing CAD."""
from itertools import product
import unittest

from vault.assembly import assembly_definition, transform_point
from vault.assembly_validation import definition_errors
from vault.generator import Configuration, ASSEMBLY_PARTS, ACCESSORY_PARTS


class AssemblyDefinitionTests(unittest.TestCase):
    def test_all_configurations_have_complete_rigid_instances(self):
        for family, depth, height, floor, rear in product('SML', range(3, 8), (1, 2), (.8, 3.), (.9, 2.)):
            configuration = Configuration(family, depth, height, 'set', floor, rear)
            scene = assembly_definition(configuration)
            instances = scene['instances']
            with self.subTest(configuration=configuration):
                self.assertEqual(len(instances), 5 + 4 * height)
                self.assertEqual(len({item['id'] for item in instances}), len(instances))
                self.assertEqual({item['kind'] for item in instances}, set(ASSEMBLY_PARTS))
                self.assertTrue(set(ACCESSORY_PARTS).isdisjoint(item["kind"] for item in instances))
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

    def test_two_columns_repeat_complete_s_drawers_at_measured_centers(self):
        for depth, height, rear, rows in product(range(3, 8), (1, 2), (.9, 2.), (1, 2)):
            if rows > height:
                continue
            config = Configuration('L', depth, height, module_rear=rear,
                                   drawer_columns=2, drawer_rows=rows)
            scene = assembly_definition(config)
            self.assertEqual(definition_errors(config, scene), [])
            self.assertEqual(len(scene['instances']), 1 + 2 * rows * (4 + 4 * height // rows))
            reference = assembly_definition(Configuration('S', depth, height // rows, module_rear=rear))
            origins = ((-82.4, 0), (82.4, 0)) if rows == 1 else (
                (-82.4, 0), (82.4, 0), (-82.4, 48), (82.4, 48))
            for bay, (center, elevation) in enumerate(origins, start=1):
                for original in reference['instances'][1:]:
                    instance = next(item for item in scene['instances']
                                    if item['id'] == f'bay_{bay}_{original["id"]}')
                    self.assertEqual(instance['bay'], bay)
                    self.assertEqual(instance['component'], original['component'])
                    for point in ((0, 0, 0), (1, 2, 3)):
                        expected = transform_point(original['transform'], point)
                        actual = transform_point(instance['transform'], point)
                        for a, b in zip(actual, (expected[0] + center, expected[1], expected[2] + elevation)):
                            self.assertAlmostEqual(a, b)
            self.assertEqual(scene['instances'][0]['transform'][12:15], [0., 0., 0.])

    def test_multi_drawer_configuration_rejects_unsupported_or_untyped_layouts(self):
        self.assertEqual(Configuration().drawer_columns, 1)
        self.assertEqual(Configuration('L').drawer_family, 'L')
        self.assertEqual(Configuration('L', drawer_columns=2).drawer_family, 'S')
        for family, columns in (('S', 2), ('M', 2), ('L', 0), ('L', 3),
                                ('L', True), ('L', 2.), ('L', '2'), ('L', None)):
            with self.subTest(family=family, columns=columns), self.assertRaises(ValueError):
                Configuration.parse({'family': family, 'drawer_columns': columns})

    def test_four_drawers_require_two_columns_in_l_2f(self):
        config = Configuration('L', 6, 2, drawer_columns=2, drawer_rows=2)
        self.assertEqual(config.drawer_height_units, 1)
        self.assertEqual(config.drawer_count, 4)
        self.assertEqual(Configuration('L', 6, 2, drawer_columns=2).drawer_height_units, 2)
        for values in ({'family': 'L', 'height_units': 1}, {'family': 'S'}, {'family': 'M'},
                       {'drawer_columns': 1}, {'drawer_rows': 0}, {'drawer_rows': 3},
                       {'drawer_rows': 2.0}, {'drawer_rows': True}, {'drawer_rows': '2'},
                       {'drawer_rows': None}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Configuration.parse(config.as_dict() | values)

    def test_print_quantities_repeat_drawers_and_tier_hardware(self):
        single = Configuration('L', 6, 2).print_copies
        double = Configuration('L', 6, 2, drawer_columns=2).print_copies
        self.assertEqual(double['module'], 1)
        for kind in ('box', 'facade', 'rails', 'key', 'spring', 'latch', 'key_cap'):
            self.assertEqual(double[kind], 2)
        self.assertEqual(double['runner_guides'], 4)
        self.assertEqual(double['runner_slides'], 4)
        self.assertEqual(double['runner_stop'], 8)
        self.assertEqual(double['facade_cap'], 8)
        self.assertEqual(single['facade_cap'], 6)
        four = Configuration('L', 6, 2, drawer_columns=2, drawer_rows=2).print_copies
        self.assertEqual(four['module'], 1)
        for kind in ('box', 'facade', 'rails', 'key', 'spring', 'latch', 'key_cap',
                     'runner_guides', 'runner_slides'):
            self.assertEqual(four[kind], 4)
        self.assertEqual(four['runner_stop'], 8)
        self.assertEqual(four['facade_cap'], 8)

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
