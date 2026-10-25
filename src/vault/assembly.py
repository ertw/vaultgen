"""Authoritative finished-drawer placements, shared by CAD checks and the viewer.

The assembly datum is the module's native frame: X across its width, Y from
closed back toward the facade, Z upward. Each rigid transform maps a component's
native geometry into that frame; it never infers a placement from mesh bounds.
Matrices use the column-major convention consumed by WebGL/Three.js. Print
orientation is separate export metadata, not part of the assembly definition.

The exploded pose is explanatory, not a certified insertion/removal path.
Every instance's ``explode`` includes its group's displacement, allowing the
viewer to interpolate directly without changing its assembled transform.
"""
from __future__ import annotations

from .generator import Configuration
from .spec import DEFAULT_SPEC, ModuleSpec


SCHEMA = 'vault-assembly/v1'
COLORS = {
    'module': '#88a9c0', 'box': '#e1b46a', 'facade': '#bd91cc',
    'rails': '#ee927b', 'runner_guides': '#76b5a4', 'runner_slides': '#aabd70',
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

    Tall drawers have one box/facade and repeat runner pairs on every tier;
    their two geared rails remain at the bottom lock. Rails are shown at
    zero locking travel (unlocked), the insertion pose in the fit checks.
    """
    if not isinstance(configuration, Configuration):
        raise TypeError('configuration must be a Configuration')
    spec = ModuleSpec(configuration.family, configuration.depth_units,
                      configuration.height_units, configuration.module_rear)
    width_delta = (spec.width - DEFAULT_SPEC.width) / 2
    depth_delta = spec.depth - DEFAULT_SPEC.depth
    drawer_explode = (0, spec.depth * .8, 0)
    lateral_explode = max(45, spec.width * .25)
    instances = []

    def add(identifier, kind, component, label, group, rotation=IDENTITY_ROTATION,
            translation=(0, 0, 0), explode=(0, 0, 0), **metadata):
        displacement = drawer_explode if group == 'drawer' else (0, 0, 0)
        instances.append({
            'id': identifier, 'kind': kind, 'component': component, 'label': label,
            'group': group, 'parent': group,
            'transform': rigid_transform(rotation, translation),
            'explode': [float(a + b) for a, b in zip(displacement, explode)],
            'color': COLORS[kind], **metadata,
        })

    add('module', 'module', 'single', spec.name, 'shell')
    add('box', 'box', 'single', f'{spec.family}{spec.depth_units} Box {spec.height_units}F', 'drawer')
    add('facade', 'facade', 'single', f'{spec.family}{spec.height_units}F Facade', 'drawer',
        translation=(0, spec.depth, 0), explode=(0, 65, 0))

    # These proper rotations preserve the source rail handedness. The retained
    # rail's rib faces upward; the plain rail's teeth face upward. Width changes
    # only their outgoing tails, not the nose datums or the centered lock.
    add('rail_plain', 'rails', 'plain', 'Lower plain geared rail', 'drawer',
        rotation=((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
        translation=(66.1, 183.1 + depth_delta, 6.807),
        explode=(-lateral_explode, 25, -25))
    add('rail_retained', 'rails', 'retained', 'Upper retained geared rail', 'drawer',
        rotation=((1, 0, 0), (0, 0, 1), (0, -1, 0)),
        translation=(-66.1, 183.1 + depth_delta, 40.193),
        explode=(lateral_explode, 25, 25))

    for kind in ('runner_guides', 'runner_slides'):
        for tier, offset in enumerate(spec.tier_offsets, start=1):
            for side, name in ((-1, 'left'), (1, 'right')):
                rotation = ((0, 0, -side), (0, 1, 0), (side, 0, 0))
                guide = kind == 'runner_guides'
                translation = ((side * (78.7 + width_delta), 2.3, 23.5 + offset - side * 13.5)
                               if guide else
                               (side * (73.9 + width_delta), 28.1, 23.5 + offset))
                add(f'{kind}_{name}_{tier}', kind, name,
                    f'{name.title()} runner {"guide" if guide else "slide"} · tier {tier}',
                    'shell' if guide else 'drawer', rotation, translation,
                    explode=(side * lateral_explode, 0, (tier - 1) * 25),
                    tier=tier, side=side)

    return {
        'schema': SCHEMA, 'units': 'mm', 'coordinates': 'native-module',
        'matrix_order': 'column-major', 'configuration': configuration.as_dict(),
        'rail_travel_mm': 0,
        'groups': [{'id': 'shell', 'label': 'Module and fixed guides'},
                   {'id': 'drawer', 'label': 'Drawer and attached parts'}],
        'instances': instances,
        'omissions': ['Lock and drive pinion', 'Screws', 'Separate runner stoppers'],
        'notes': ['Finished parts: module webs and box runner sheets removed.',
                  'Geared rails shown unlocked at zero locking travel.',
                  'Exploded spacing illustrates components; it is not a disassembly path.'],
    }


def build_finished_components(configuration: Configuration):
    """Build native solids for the unique components referenced by a definition.

    The keys are ``(kind, component)`` pairs from ``assembly_definition``.
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
    family, depth, height = configuration.family, configuration.depth_units, configuration.height_units
    guides = build_runner_guide(spec=RunnerGuideSpec(depth))
    slides = build_runner_slide(spec=RunnerSlideSpec(depth))
    return {
        ('module', 'single'): build_module(
            spec=ModuleSpec(family, depth, height, configuration.module_rear), include_supports=False),
        ('box', 'single'): build_box(
            spec=BoxSpec(family, depth, height, configuration.box_floor), include_supports=False),
        ('facade', 'single'): build_facade(spec=FacadeSpec(family, height)),
        ('rails', 'plain'): build_gear_rail(False, spec=GearRailSpec(family)),
        ('rails', 'retained'): build_gear_rail(True, spec=GearRailSpec(family)),
        ('runner_guides', 'left'): guides, ('runner_guides', 'right'): guides,
        ('runner_slides', 'left'): slides, ('runner_slides', 'right'): slides,
    }
