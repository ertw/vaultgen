"""Assembly invariants across all supported sizes without importing CAD."""
from itertools import product
from collections import Counter
import unittest

from vault.assembly import assembly_definition, transform_point
from vault.assembly_validation import definition_errors
from vault.drawer import DrawerLayout
from vault.generator import Configuration, ASSEMBLY_PARTS, ACCESSORY_PARTS
from vault.spec import ModuleSpec


class AssemblyDefinitionTests(unittest.TestCase):
    def test_all_configurations_have_complete_rigid_instances(self):
        for family, depth, height, floor, rear in product('SML', range(3, 8), (1, 2), (.8, 3.), (.9, 2.)):
            configuration = Configuration(family, depth, height, 'set', floor, rear)
            scene = assembly_definition(configuration)
            instances = scene['instances']
            with self.subTest(configuration=configuration):
                self.assertEqual(len(instances), {'S': 10, 'M': 12, 'L': 13}[family] + 8 * height)
                self.assertEqual(len({item['id'] for item in instances}), len(instances))
                self.assertEqual({item['kind'] for item in instances}, set(ASSEMBLY_PARTS + ACCESSORY_PARTS))
                expected = {kind: copies * (2 if kind in ('rails', 'runner_guides', 'runner_slides') else 1)
                            for kind, copies in configuration.print_copies.items()}
                self.assertEqual(Counter(item['kind'] for item in instances), expected)
                self.assertEqual(definition_errors(configuration, scene), [])
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
            self.assertEqual(len(scene['instances']), 3 + 2 * rows * (8 + 8 * height // rows))
            reference = assembly_definition(Configuration('S', depth, height // rows, module_rear=rear))
            origins = ((-82.4, 0), (82.4, 0)) if rows == 1 else (
                (-82.4, 0), (82.4, 0), (-82.4, 48), (82.4, 48))
            for bay, (center, elevation) in enumerate(origins, start=1):
                for original in (item for item in reference['instances']
                                 if item['kind'] not in ('module', 'latch')):
                    instance = next(item for item in scene['instances']
                                    if item['id'] == f'bay_{bay}_{original["id"]}')
                    self.assertEqual(instance['bay'], bay)
                    self.assertEqual(instance['component'], original['component'])
                    for point in ((0, 0, 0), (1, 2, 3)):
                        expected = transform_point(original['transform'], point)
                        actual = transform_point(instance['transform'], point)
                        for a, b in zip(actual, (expected[0] + center, expected[1], expected[2] + elevation)):
                            self.assertAlmostEqual(a, b)
            self.assertEqual(scene['instances'][0]['transform'][12:15], [0., 0., float(48 * height - 1)])

    def test_module_latch_face_points_down_while_drawer_stays_upright(self):
        for family, depth, height in product('SML', range(3, 8), (1, 2)):
            scene = assembly_definition(Configuration(family, depth, height))
            module = scene['instances'][0]['transform']
            skin_height = 48 * height - 1
            self.assertEqual(transform_point(module, (0, 0, 0)), (0, 0, skin_height))
            self.assertEqual(transform_point(module, (0, 0, skin_height)), (0, 0, 0))
            self.assertEqual(transform_point(module, (10, 20, skin_height + 4)), (-10, 20, -4))
            box = next(item['transform'] for item in scene['instances'] if item['kind'] == 'box')
            self.assertEqual(transform_point(box, (0, 20, 5)), (0, 20, 5))

    def test_facade_caps_share_every_screw_axis_and_face_seat(self):
        configurations = [Configuration(family, depth, height)
                          for family, depth, height in product('SML', range(3, 8), (1, 2))]
        configurations += [Configuration('L', depth, height, drawer_columns=2, drawer_rows=rows)
                           for depth, height, rows in product(range(3, 8), (1, 2), (1, 2))
                           if rows <= height]
        for config in configurations:
            module = ModuleSpec(config.family, config.depth_units, config.height_units,
                                drawer_columns=config.drawer_columns, drawer_rows=config.drawer_rows)
            drawer = ModuleSpec(config.drawer_family, config.depth_units, config.drawer_height_units)
            caps = [item for item in assembly_definition(config)['instances'] if item['kind'] == 'facade_cap']
            expected = {(center + x, module.depth + 10, elevation + z)
                        for center, elevation in module.drawer_origins
                        for x, z in DrawerLayout(drawer).screw_positions}
            with self.subTest(configuration=config):
                self.assertEqual({transform_point(cap['transform'], (0, 0, 0)) for cap in caps}, expected)
                self.assertEqual(len(caps), len(expected))
                for cap in caps:
                    self.assertEqual(cap['placement'], 'installed')
                    self.assertEqual(cap['group'], 'drawer')
                    seat = transform_point(cap['transform'], (0, 0, 0))
                    tip = transform_point(cap['transform'], (0, 0, 3.8))
                    self.assertEqual(tip[::2], seat[::2])
                    self.assertAlmostEqual(tip[1], seat[1] - 3.8)

    def test_accessories_are_installed_and_repeat_by_drawer_or_module_bank(self):
        cases = [('S', 1, 1, 1, 18), ('S', 2, 1, 1, 26),
                 ('M', 1, 1, 1, 20), ('M', 2, 1, 1, 28),
                 ('L', 1, 1, 1, 21), ('L', 2, 1, 1, 29),
                 ('L', 1, 2, 1, 35), ('L', 2, 2, 1, 51), ('L', 2, 2, 2, 67)]
        for family, height, columns, rows, count in cases:
            config = Configuration(family, 4, height, drawer_columns=columns, drawer_rows=rows)
            scene = assembly_definition(config)
            accessories = [item for item in scene['instances'] if item['kind'] in ACCESSORY_PARTS]
            with self.subTest(configuration=config):
                self.assertEqual(len(scene['instances']), count)
                self.assertEqual({item['placement'] for item in scene['instances']}, {'installed'})
                self.assertEqual({group['id'] for group in scene['groups']}, {'shell', 'drawer'})
                self.assertEqual(scene['omissions'], ['Screws'])
                self.assertEqual(scene['validation_scope'], 'drawer_components')
                for item in accessories:
                    self.assertNotIn('loose', item['label'].lower())
                    fixed = item['kind'] in ('latch', 'runner_stop')
                    self.assertEqual(item['group'], 'shell' if fixed else 'drawer')
                    # Fixed hardware stays with the housing when exploded;
                    # attached lock parts follow the facade out of the drawer.
                    if fixed:
                        self.assertEqual(item['explode'][1], 0)
                    else:
                        self.assertGreater(item['explode'][1], 0)
                self.assertEqual(sum(item['kind'] == 'spring' for item in accessories), 2 * columns * rows)
                latches = [item for item in accessories if item['kind'] == 'latch']
                self.assertEqual(len(latches), 2 if family == 'L' else 1)
                self.assertTrue(all('bay' not in item for item in latches))

    def test_lock_hardware_registers_to_facade_seats_in_every_drawer(self):
        configurations = [Configuration(family, depth, height)
                          for family, depth, height in product('SML', range(3, 8), (1, 2))]
        configurations += [Configuration('L', depth, height, drawer_columns=2, drawer_rows=rows)
                           for depth, height, rows in product(range(3, 8), (1, 2), (1, 2))
                           if rows <= height]
        # Circle through the three native fork points; independent of the
        # assembly's translation constant and the family's outside width.
        fork_x = (19.9**2 - 10.6**2 - 6.325**2) / (2 * (19.9 - 10.6))
        for config in configurations:
            instances = assembly_definition(config)['instances']
            for facade in (item for item in instances if item['kind'] == 'facade'):
                bay = facade.get('bay', 1)
                hardware = [item for item in instances if item.get('bay', 1) == bay]
                key = next(item for item in hardware if item['kind'] == 'key')
                cap = next(item for item in hardware if item['kind'] == 'key_cap')
                with self.subTest(configuration=config, bay=bay):
                    actual = transform_point(key['transform'], (0, 0, 18.4))
                    expected = transform_point(facade['transform'], (0, 10, 23.5))
                    for a, b in zip(actual, expected):
                        self.assertAlmostEqual(a, b)
                    for point in ((0, 0, 0), (3, 2, 7)):
                        expected = transform_point(key['transform'],
                                                   (point[0], -point[1], 35.517 - point[2]))
                        actual = transform_point(cap['transform'], point)
                        for a, b in zip(actual, expected):
                            self.assertAlmostEqual(a, b)
                    for spring in (item for item in hardware if item['kind'] == 'spring'):
                        actual = transform_point(spring['transform'], (fork_x, 0, 5.155))
                        expected = transform_point(facade['transform'],
                                                   (spring['side'] * 51.45, 5.75, 23.5))
                        for a, b in zip(actual, expected):
                            self.assertAlmostEqual(a, b)

    def test_fixed_accessories_face_into_slots_and_out_from_underside(self):
        for family, depth, height, columns, rows in product('SML', range(3, 8), (1, 2), (1, 2), (1, 2)):
            if (columns == 2 and family != 'L') or (rows == 2 and (columns != 2 or height != 2)):
                continue
            config = Configuration(family, depth, height, drawer_columns=columns, drawer_rows=rows)
            spec = ModuleSpec(family, depth, height, drawer_columns=columns, drawer_rows=rows)
            scene = assembly_definition(config)
            half_width = (164.8 if columns == 2 else spec.width) / 2
            for instance in scene['instances']:
                with self.subTest(configuration=config, instance=instance['id']):
                    matrix = instance['transform']
                    if instance['kind'] == 'runner_stop':
                        center, elevation = spec.drawer_origins[instance.get('bay', 1) - 1]
                        side = instance['side']
                        flange = transform_point(matrix, (0, 0, 0))
                        tip = transform_point(matrix, (0, 0, 8.188))
                        self.assertAlmostEqual(flange[0], center + side * half_width)
                        self.assertAlmostEqual(tip[0], center + side * (half_width - 8.188))
                        self.assertAlmostEqual(flange[1], spec.depth / 2 + 28.50005)
                        self.assertAlmostEqual(flange[2], 47 - 23.5009 + elevation
                                               + 48 * (instance['tier'] - 1))
                        self.assertEqual(tip[1:], flange[1:])
                    elif instance['kind'] == 'latch':
                        center = spec.bank_centers[instance['bank'] - 1]
                        hook = transform_point(matrix, (30.6729035525, 34.0533015629, 0))
                        # The relieved hook's inner radius exceeds the lobe
                        # radius by enough to accommodate their X offset.
                        self.assertLess(abs(hook[0] - (center - 30.4062)), .267)
                        self.assertAlmostEqual(hook[1], 60.481)
                        self.assertEqual(hook[2], 0)
                        self.assertEqual(transform_point(matrix, (0, 0, 4.35))[2], -4.35)

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
        for kind in ('box', 'facade', 'rails', 'key', 'key_cap'):
            self.assertEqual(double[kind], 2)
        self.assertEqual(double['spring'], 4)
        self.assertEqual(double['latch'], 2)
        self.assertEqual(double['runner_guides'], 4)
        self.assertEqual(double['runner_slides'], 4)
        self.assertEqual(double['runner_stop'], 8)
        self.assertEqual(double['facade_cap'], 8)
        self.assertEqual(single['facade_cap'], 6)
        four = Configuration('L', 6, 2, drawer_columns=2, drawer_rows=2).print_copies
        self.assertEqual(four['module'], 1)
        for kind in ('box', 'facade', 'rails', 'key', 'key_cap',
                     'runner_guides', 'runner_slides'):
            self.assertEqual(four[kind], 4)
        self.assertEqual(four['spring'], 8)
        self.assertEqual(four['latch'], 2)
        self.assertEqual(single['spring'], 2)
        self.assertEqual(single['latch'], 2)
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
