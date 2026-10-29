"""Inspect installed accessory datums and nominal native intersections.

Run after sourcing .local-env::

    python tools/check_accessory_assembly.py --case S4:1
    python tools/check_accessory_assembly.py --case L6x2x2:2

This is a placement diagnostic, not an accessory fit receipt. Positive-volume
intersections are reported without being reclassified as acceptable fit. The
key collar, snap stems and flexible parts need separate insertion, retention
and printed-fit qualification. The normal six-group drawer audit is unchanged.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from itertools import combinations
import json
from math import dist
from pathlib import Path

from check_assembly import parse_case
from vault.assembly import (
    apply_transform, assembly_definition, build_finished_components, transform_point,
)
from vault.assembly_validation import (
    bounds_gap, definition_errors, intersection_volume,
)
from vault.generator import Configuration
from vault.spec import ModuleSpec


ACCESSORIES = frozenset(('key', 'key_cap', 'spring', 'runner_stop', 'facade_cap', 'latch'))


def circle_center(a, b, c):
    """Center of a native three-point arc, without assuming a nominal radius."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    denominator = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    aa, bb, cc = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    return ((aa * (by - cy) + bb * (cy - ay) + cc * (ay - by)) / denominator,
            (aa * (cx - bx) + bb * (ax - cx) + cc * (bx - ax)) / denominator)


def datum_checks(configuration, definition):
    """Register mating features, independently of the scene's translations."""
    from vault.key_geometry import D as key_dimensions
    from vault.alignment_features import LockingBridgeDimensions
    from vault.shell import ShellDimensions

    spec = ModuleSpec(configuration.family, configuration.depth_units,
                      configuration.height_units, configuration.module_rear,
                      configuration.drawer_columns, configuration.drawer_rows)
    drawer_spec = ModuleSpec(configuration.drawer_family, configuration.depth_units,
                             configuration.drawer_height_units)
    checks = []

    def point(instance, name, native, expected):
        actual = transform_point(instance['transform'], native)
        error = dist(actual, expected)
        checks.append({'instance': instance['id'], 'datum': name,
                       'actual_mm': actual, 'expected_mm': expected,
                       'error_mm': error, 'passed': error < 1e-6})

    for instance in definition['instances']:
        kind = instance['kind']
        center, elevation = spec.drawer_origins[instance.get('bay', 1) - 1]
        axis_z = 23.5 + elevation
        if kind == 'key':
            point(instance, 'shoulder at facade front', (0, 0, key_dimensions.shoulder_top),
                  (center, spec.depth + 10, axis_z))
            point(instance, 'shaft points toward facade front', (0, 0, key_dimensions.shoulder_top + 1),
                  (center, spec.depth + 11, axis_z))
        elif kind == 'key_cap':
            # Existing cap seated-pose diagnostic leaves 0.1 mm over the handle.
            point(instance, 'socket ceiling over handle end', (0, 0, 2),
                  (center, spec.depth + 10 - key_dimensions.shoulder_top
                   + key_dimensions.handle_top + .1, axis_z))
        elif kind == 'spring':
            # Analytic center of its native three-point circular seating arc.
            fork_x = (19.9 ** 2 - 10.6 ** 2 - 6.325 ** 2) / (2 * (19.9 - 10.6))
            side = 1 if instance['transform'][0] > 0 else -1
            point(instance, 'fork axis and pocket floor', (fork_x, 0, 5.155),
                  (center + side * 51.45, spec.depth + 5.75, axis_z))
            point(instance, 'flat rear face', (fork_x, 0, 0),
                  (center + side * 51.45, spec.depth + 5.75 - 5.155, axis_z))
        elif kind == 'runner_stop':
            # The housing is inverted in the installed frame. Its source oval
            # center therefore becomes height - the native opening center.
            shell = ShellDimensions()
            side, tier = instance['side'], instance['tier']
            point(instance, 'flange center at side opening', (0, 0, 0),
                  (center + side * drawer_spec.half_width,
                   spec.depth / 2 + shell.stopper_center_offset,
                   drawer_spec.height - drawer_spec.tier_offsets[-1] - shell.stopper_center_z
                   + drawer_spec.tier_offsets[tier - 1] + elevation))
        elif kind == 'latch':
            bridge = LockingBridgeDimensions()
            bank_center = spec.bank_centers[instance['bank'] - 1]
            hook_x, hook_y = circle_center((28.263, 31.875), (27.613, 35.144), (30.385, 37.289))
            # The hook arcs share the carrier lobe's Y station. Their X axes
            # differ nominally; this is not a claimed fit clearance.
            point(instance, 'hook station on underside skin', (0, hook_y, 0),
                  (bank_center, bridge.arm_lobe_y, 0))
            point(instance, 'latch thickness projects below skin', (0, hook_y, 1),
                  (bank_center, bridge.arm_lobe_y, -1))
            checks[-2]['nominal_hook_to_carrier_lobe_axis_offset_x_mm'] = (
                hook_x - bridge.arm_lobe_center_x)
    return checks


def inspect(configuration, native_accessories):
    definition = assembly_definition(configuration)
    errors = definition_errors(configuration, definition)
    datums = datum_checks(configuration, definition)
    native = build_finished_components(configuration)
    native.update(native_accessories)
    placed, solids = [], []
    for instance in definition['instances']:
        shape = apply_transform(native[instance['kind'], instance['component']], instance['transform'])
        if instance['kind'] in ACCESSORIES:
            solids.append({'instance': instance['id'], 'valid': shape.is_valid,
                           'solid_count': len(shape.solids()), 'volume_mm3': shape.volume})
        placed.append((instance, shape))
    observations = []
    for (left, a), (right, b) in combinations(placed, 2):
        if left['kind'] not in ACCESSORIES and right['kind'] not in ACCESSORIES:
            continue
        gap = bounds_gap(a, b)
        if gap > 1e-6:
            continue
        volume = intersection_volume(a, b)
        observations.append({'instances': [left['id'], right['id']],
                             'intersection_volume_mm3': volume,
                             'minimum_gap_mm': a.distance_to(b),
                             'positive_volume_intersection': volume > 1e-5})
    return {'configuration': configuration.as_dict(), 'definition_errors': errors,
            'datum_checks': datums, 'accessory_solids': solids,
            'native_observations': observations,
            'registration_passed': (not errors and all(check['passed'] for check in datums)
                                    and all(item['valid'] and item['solid_count'] == 1 for item in solids)),
            'accessory_fit_certified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=parse_case, action='append')
    parser.add_argument('--facade-floor', choices=('0.8', 'default'), default='default')
    parser.add_argument('--output', type=Path, default=Path('out/reviews/accessory-assembly.json'))
    args = parser.parse_args()
    from vault.accessories import build_facade_cap, build_key_cap, build_runner_stop, build_spring
    from vault.key import build_key
    from vault.latch import build_latch

    print('Building native accessories', flush=True)
    accessories = {('key', 'key'): build_key(), ('key_cap', 'single'): build_key_cap(),
                   ('spring', 'single'): build_spring(), ('runner_stop', 'single'): build_runner_stop(),
                   ('facade_cap', 'single'): build_facade_cap(), ('latch', 'single'): build_latch()}
    cases = []
    for configuration in args.case or [Configuration('S', 4, 1)]:
        configuration = replace(configuration,
                                facade_floor=.8 if args.facade_floor == '0.8' else 'default')
        print(f'Inspecting {configuration.as_dict()}', flush=True)
        case = inspect(configuration, accessories)
        cases.append(case)
        overlaps = [pair for pair in case['native_observations'] if pair['positive_volume_intersection']]
        print(json.dumps({'registration_passed': case['registration_passed'],
                          'nominal_intersections': overlaps}), flush=True)
    report = {'schema': 'vault-accessory-placement-diagnostic/v1', 'units': 'mm',
              'cases': cases, 'registration_passed': all(case['registration_passed'] for case in cases),
              'accessory_fit_certified': False,
              'limitations': 'Installed datum registration and undeformed native intersection observations only. '
                             'Reported intersections remain unresolved fit observations, not accepted clearances. '
                             'No insertion motion, snap retention, spring deflection, gear travel, fatigue or '
                             'physical print fit is certified. Separated bounds pairs are omitted. '
                             'The normal six-group drawer fit receipt excludes these accessory interfaces.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Accessory placement report: {args.output}', flush=True)
    if not report['registration_passed']:
        raise SystemExit('Accessory datum registration failed')


if __name__ == '__main__':
    main()
