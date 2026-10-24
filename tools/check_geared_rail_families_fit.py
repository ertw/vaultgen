"""Check M3 1F and L4 2F rail poses against their native box and sleeve.

This is a sampled clearance check at 0/10/20 mm, with a 21 mm stop-contact
positive control. It does not extend the S continuous-sweep certificate to
M/L, whose source tails have a different transition into the extended shank.
"""
from dataclasses import replace
import json

from vault.box import build_box
from vault.geared_rails import GearRailSpec, build_gear_rail
from vault.reference import PROJECT_ROOT
from vault.shell import ShellDimensions, build_shell
from vault.spec import DEFAULT_SPEC, ModuleSpec

if __package__:
    from .check_geared_rails import common_volume, place_gear_rail
else:
    from check_geared_rails import common_volume, place_gear_rail


def main():
    poses = []
    for spec in (ModuleSpec('M', 3, 1), ModuleSpec('L', 4, 2)):
        box = build_box(spec=spec)
        module = build_shell(spec=spec, dimensions=replace(
            ShellDimensions(), pocket_support_thickness=0))
        for retained in (False, True):
            part = build_gear_rail(retained, spec=GearRailSpec(spec.family))
            for travel in (0, 10, 20, 21):
                # The source tooth mechanism remains centered on the lock.
                # Only the outgoing tail extends with family width. Both rails
                # stay at the bottom tier when the box is 2F tall.
                rail = place_gear_rail(part, retained, travel).translate(
                    (0, spec.depth - DEFAULT_SPEC.depth, 0))
                item = {
                    'family': spec.family, 'depth_units': spec.depth_units,
                    'height_units': spec.height_units, 'retained': retained,
                    'travel': travel, 'box_distance': rail.distance_to(box),
                    'module_distance': rail.distance_to(module),
                    'module_overlap_mm3': common_volume(rail, module),
                }
                poses.append(item)
                print(json.dumps(item), flush=True)
    report = {
        'schema': 'vault-geared-rail-families-fit/v1', 'units': 'mm',
        'method': 'Native solid minimum distance and Boolean overlap at sampled positions; '
                  'not a continuous sweep certificate. Rails share source nose and tooth '
                  'registration, with family tails extended by half the module width '
                  'increase. Module sacrificial supports removed.',
        'poses': poses,
        'passed': all(
            pose['box_distance'] > .19 and (
                pose['module_distance'] > .08 and pose['module_overlap_mm3'] < 1e-5
                if pose['travel'] <= 20 else pose['module_overlap_mm3'] > .01)
            for pose in poses),
    }
    destination = PROJECT_ROOT / 'research/geared_rail_families_fit.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'report': str(destination)}), flush=True)
    if not report['passed']:
        raise SystemExit('Geared rail family sampled fit check failed')


if __name__ == '__main__':
    main()
