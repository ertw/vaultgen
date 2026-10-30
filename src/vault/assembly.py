"""Authoritative finished-drawer placements, shared by CAD checks and the viewer.

The assembly datum has X across the width, Y from closed back toward the facade,
and Z upward from the installed module's lower skin. The module's native frame
has its latch carrier above its body; its installed pose turns that face down.
Each rigid transform maps a component's
native geometry into that frame; it never infers a placement from mesh bounds.
Matrices use the column-major convention consumed by WebGL/Three.js. Print
orientation is separate export metadata, not part of the assembly definition.

The exploded pose is explanatory, not a certified insertion/removal path.
Every instance's ``explode`` includes its group's displacement, allowing the
viewer to interpolate directly without changing its assembled transform.
"""
from __future__ import annotations

from .drawer import DrawerLayout
from .generator import Configuration
from .spec import DEFAULT_SPEC, ModuleSpec, WALL_PATTERNS, pattern_parameters, wall_parameters


SCHEMA = 'vault-assembly/v1'
COLORS = {
    'module': '#88a9c0', 'box': '#e1b46a', 'facade': '#bd91cc',
    'rails': '#ee927b', 'runner_guides': '#76b5a4', 'runner_slides': '#aabd70',
    'key': '#ee927b', 'spring': '#ee927b', 'runner_stop': '#76b5a4',
    'facade_cap': '#bd91cc', 'key_cap': '#bd91cc', 'latch': '#ee927b',
}
IDENTITY_ROTATION = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def rigid_transform(rotation=IDENTITY_ROTATION, translation=(0, 0, 0)):
    """Serialize a native-to-assembly rigid transform in column-major order."""
    return [float(rotation[row][column]) if row < 3 else 0.0
            for column in range(3) for row in range(4)] + [*map(float, translation), 1.0]


def transform_point(matrix, point):
    """Apply the same serialized transform used by the browser to a 3D point."""
    return tuple(sum(matrix[column * 4 + row] * point[column] for column in range(3))
                 + matrix[12 + row] for row in range(3))


def apply_transform(shape, matrix):
    """Place a copy of a native CAD shape with a serialized assembly transform."""
    from build123d import Matrix
    from OCP.gp import gp_Trsf
    # A Matrix constructed from a nested list retains OCC's generic affine
    # form flag even for exact orthogonal matrices; set a rigid gp_Trsf first.
    transform = gp_Trsf()
    transform.SetValues(*(matrix[column * 4 + row] for row in range(3) for column in range(4)))
    return shape.transform_shape(Matrix(transform))


def assembly_definition(configuration: Configuration):
    """Return the complete configured drawer, independent of selected part.

    Each drawer has one box/facade and repeats runner pairs on every tier;
    its two geared rails remain at the bottom lock. Rails are shown at
    zero locking travel (unlocked), the insertion pose in the fit checks.
    Accessories use the lock, screw, stopper-slot and connector-bank datums.
    Their installed display poses do not certify snap retention or motion.
    """
    if not isinstance(configuration, Configuration):
        raise TypeError('configuration must be a Configuration')
    spec = ModuleSpec(configuration.family, configuration.depth_units,
                      configuration.height_units, configuration.module_rear,
                      configuration.drawer_columns, configuration.drawer_rows,
                      **{**pattern_parameters(configuration), **wall_parameters(configuration)})
    drawer_spec = ModuleSpec(configuration.drawer_family, configuration.depth_units,
                             configuration.drawer_height_units, configuration.module_rear)
    width_delta = (drawer_spec.width - DEFAULT_SPEC.width) / 2
    depth_delta = spec.depth - DEFAULT_SPEC.depth
    drawer_explode = (0, spec.depth * .8, 0)
    lateral_explode = max(45, drawer_spec.width * .25)
    instances = []

    def add(identifier, kind, component, label, group, rotation=IDENTITY_ROTATION,
            translation=(0, 0, 0), explode=(0, 0, 0), **metadata):
        displacement = drawer_explode if group == 'drawer' else (0, 0, 0)
        instances.append({
            'id': identifier, 'kind': kind, 'component': component, 'label': label,
            'group': group, 'parent': group,
            'transform': rigid_transform(rotation, translation),
            'explode': [float(a + b) for a, b in zip(displacement, explode)],
            'color': COLORS[kind], 'placement': 'installed', **metadata,
        })

    # Native Z=0 is the original marked top, while native Z=height carries
    # the underside latch tracks. Turn only the housing upright, preserving
    # the +Y opening and the opposed runner mouths; drawers already have Z up.
    add('module', 'module', 'single', spec.name, 'shell',
        rotation=((-1, 0, 0), (0, 1, 0), (0, 0, -1)),
        translation=(0, 0, spec.height))
    for bay, (center, elevation) in enumerate(spec.drawer_origins, start=1):
        def add_drawer(identifier, kind, component, label, group,
                       rotation=IDENTITY_ROTATION, translation=(0, 0, 0), **metadata):
            if configuration.drawer_columns > 1:
                identifier = f'bay_{bay}_{identifier}'
                label += f' · drawer {bay}'
                metadata['bay'] = bay
            add(identifier, kind, component, label, group, rotation,
                (translation[0] + center, translation[1], translation[2] + elevation), **metadata)

        add_drawer('box', 'box', 'single',
                   f'{drawer_spec.family}{spec.depth_units} Box {drawer_spec.height_units}F'
                   + (' · Floorless' if configuration.box_floor == 0 else '')
                   + (' · Gridfinity' if configuration.box_variant == 'gridfinity' else '')
                   + (f' · {WALL_PATTERNS[configuration.box_rear_pattern]} corrugated rear'
                      if configuration.box_rear_pattern != 'plain' else '')
                   + (f' · {configuration.wall_perimeters} perimeter{"s" if configuration.wall_perimeters == 2 else ""}, {configuration.nozzle_size:g} mm nozzle'
                      if configuration.wall_perimeters in (1, 2) else
                      ' · Full width' if configuration.wall_perimeters == 'full' else ''), 'drawer')
        add_drawer('facade', 'facade', 'single', f'{drawer_spec.family}{drawer_spec.height_units}F Facade', 'drawer',
                   translation=(0, spec.depth, 0), explode=(0, 65, 0))
        for index, (x, z) in enumerate(DrawerLayout(drawer_spec).screw_positions, start=1):
            add_drawer(f'facade_cap_{index}', 'facade_cap', 'single',
                       f'Facade screw cap {index}', 'drawer',
                       rotation=((1, 0, 0), (0, 0, -1), (0, 1, 0)),
                       translation=(x, spec.depth + 10, z), explode=(0, 80, 0))

        # The key's native shaft is +Z. Its Z=18.4 shoulder seats at the
        # facade's Y=10 front face; the lock stays on the bottom tier.
        add_drawer('key', 'key', 'key', 'Key with drive pinion', 'drawer',
                   rotation=((1, 0, 0), (0, 0, 1), (0, -1, 0)),
                   translation=(0, spec.depth - 8.4, 23.5), explode=(0, 100, 0))
        # Compose the native cap's +180° X / Z=35.517 seated pose with
        # the key transform, retaining their shared horizontal handle axis.
        add_drawer('key_cap', 'key_cap', 'single', 'Key cap', 'drawer',
                   rotation=((1, 0, 0), (0, 0, -1), (0, 1, 0)),
                   translation=(0, spec.depth + 27.117, 23.5), explode=(0, 125, 0))
        # Register each native fork arc to the fixed ±51.45 lock screw axes.
        # Its 5.155 mm fork seats against the facade's Y=5.75 pocket floor.
        spring_fork_x = 13.099159946236556
        for index, side in enumerate((-1, 1), start=1):
            add_drawer(f'spring_{index}', 'spring', 'single', f'Spring {index}', 'drawer',
                       rotation=((side, 0, 0), (0, 0, 1), (0, -side, 0)),
                       translation=(side * (51.45 - spring_fork_x), spec.depth + .595, 23.5),
                       explode=(side * 20, 50, 0), side=side)

        # The stop's native +Z stem points inward from each bay's side face.
        # Module inversion maps its native slot Z=23.5009 to Z=23.4991.
        for tier, offset in enumerate(drawer_spec.tier_offsets, start=1):
            for side, name in ((-1, 'left'), (1, 'right')):
                add_drawer(f'runner_stop_{name}_{tier}', 'runner_stop', 'single',
                           f'{name.title()} runner stop · tier {tier}', 'shell',
                           rotation=((0, 0, -side), (0, 1, 0), (side, 0, 0)),
                           translation=(side * drawer_spec.half_width,
                                        spec.depth / 2 + 28.50005, 23.4991 + offset),
                           explode=(side * (lateral_explode + 25), 0, (tier - 1) * 25),
                           tier=tier, side=side)

        # Proper rotations preserve rail handedness. Each drawer's bottom lock
        # retains its own nose datums; a second bay only translates the drawer.
        add_drawer('rail_plain', 'rails', 'plain', 'Lower plain geared rail', 'drawer',
                   rotation=((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
                   translation=(66.1, 183.1 + depth_delta, 6.807),
                   explode=(-lateral_explode, 25, -25))
        add_drawer('rail_retained', 'rails', 'retained', 'Upper retained geared rail', 'drawer',
                   rotation=((1, 0, 0), (0, 0, 1), (0, -1, 0)),
                   translation=(-66.1, 183.1 + depth_delta, 40.193),
                   explode=(lateral_explode, 25, 25))

        for kind in ('runner_guides', 'runner_slides'):
            for tier, offset in enumerate(drawer_spec.tier_offsets, start=1):
                for side, name in ((-1, 'left'), (1, 'right')):
                    rotation = ((0, 0, -side), (0, 1, 0), (side, 0, 0))
                    guide = kind == 'runner_guides'
                    translation = ((side * (78.7 + width_delta), 2.3, 23.5 + offset - side * 13.5)
                                   if guide else
                                   (side * (73.9 + width_delta), 28.1, 23.5 + offset))
                    add_drawer(f'{kind}_{name}_{tier}', kind, name,
                               f'{name.title()} runner {"guide" if guide else "slide"} · tier {tier}',
                               'shell' if guide else 'drawer', rotation, translation,
                               explode=(side * lateral_explode, 0, (tier - 1) * 25),
                               tier=tier, side=side)

    # Latch hook arc centers at native Y=34.0533015629 register to the closed-back
    # bridge lobes at Y=60.481. Turn the print face toward the underside skin,
    # like the housing; each bank has one latch regardless of drawer count.
    for bank, center in enumerate(spec.bank_centers, start=1):
        add(f'latch_{bank}', 'latch', 'single', f'Latch · bank {bank}', 'shell',
            rotation=((-1, 0, 0), (0, 1, 0), (0, 0, -1)),
            translation=(center, 60.481 - 34.0533015629, 0), explode=(0, 0, -35), bank=bank)

    return {
        'schema': SCHEMA, 'units': 'mm', 'coordinates': 'installed-drawer',
        'matrix_order': 'column-major', 'configuration': configuration.as_dict(),
        'rail_travel_mm': 0, 'validation_scope': 'drawer_components',
        'groups': [{'id': 'shell', 'label': 'Module and fixed hardware'},
                   {'id': 'drawer', 'label': 'Drawer and attached parts'}],
        'instances': instances,
        'omissions': ['Screws'],
        'notes': ['Finished parts: module webs and box runner sheets removed.',
                  'Geared rails shown unlocked at zero locking travel.',
                  'Accessories are shown installed; their fit and retention are outside the drawer fit check.',
                  'Exploded spacing illustrates components; it is not a disassembly path.'],
    }


def build_finished_components(configuration: Configuration):
    """Build native solids for the six groups covered by drawer fit validation.

    The keys are ``(kind, component)`` pairs from ``assembly_definition``.
    Accessory display instances are outside this validation scope.
    Left/right runners have identical geometry, reused across all height tiers.
    CAD dependencies stay lazy so web requests can compose scenes cheaply.
    """
    from .box import BoxSpec, build_box
    from .facade import FacadeSpec, build_facade
    from .geared_rails import GearRailSpec, build_gear_rail
    from .model import build_module
    from .runner_guides import RunnerGuideSpec, build_runner_guide
    from .runner_slides import RunnerSlideSpec, build_runner_slide

    if not isinstance(configuration, Configuration):
        raise TypeError('configuration must be a Configuration')
    family, depth, height = configuration.drawer_family, configuration.depth_units, configuration.drawer_height_units
    guides = build_runner_guide(spec=RunnerGuideSpec(depth))
    slides = build_runner_slide(spec=RunnerSlideSpec(depth))
    return {
        ('module', 'single'): build_module(
            spec=ModuleSpec(configuration.family, depth, configuration.height_units, configuration.module_rear,
                            configuration.drawer_columns, configuration.drawer_rows,
                            **{**pattern_parameters(configuration), **wall_parameters(configuration)}), include_supports=False),
        ('box', 'single'): build_box(
            spec=BoxSpec(family, depth, height, configuration.box_floor, configuration.box_variant,
                         configuration.box_rear_pattern,
                         **(wall_parameters(configuration) if configuration.wall_perimeters is not None else {})),
            include_supports=False),
        ('facade', 'single'): build_facade(spec=FacadeSpec(family, height,
                                                        facade_floor=configuration.facade_floor)),
        ('rails', 'plain'): build_gear_rail(False, spec=GearRailSpec(family)),
        ('rails', 'retained'): build_gear_rail(True, spec=GearRailSpec(family)),
        ('runner_guides', 'left'): guides, ('runner_guides', 'right'): guides,
        ('runner_slides', 'left'): slides, ('runner_slides', 'right'): slides,
    }
