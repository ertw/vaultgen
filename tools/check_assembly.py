"""Audit the authoritative finished assembly with native solid geometry.

Run after sourcing .local-env::

    python tools/check_assembly.py --case S4:1
    python tools/check_assembly.py --case L6x2:2
    python tools/check_assembly.py --case L6x2x2:2
    python tools/check_assembly.py --representative
    python tools/check_assembly.py --all

The default representative sample covers every family, all three heights, shortest
and longest catalog depths, and all four floor/rear thickness combinations.
``--all`` checks all 260 supported combinations and is intentionally expensive.
Every run also checks the inexpensive scene definitions for all 260 cases.
Exploded translations explain the parts; this audit certifies only the closed
assembled pose, not a continuous insertion, locking, or disassembly path.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from itertools import product
import json
from pathlib import Path

from vault.assembly import assembly_definition
from vault.assembly_validation import (
    CONTACT_RULES, DISTANCE_TOLERANCE_MM, VOLUME_TOLERANCE_MM3,
    definition_errors, validate_assembly,
)
from vault.generator import Configuration
from vault.spec import DRAWER_HEIGHTS, PATTERN_DEFAULTS


def all_configurations():
    single_row = tuple(Configuration(family, depth, height, "set", floor, rear, columns)
                       for (family, columns), depth, height, floor, rear in product(
                           (("S", 1), ("M", 1), ("L", 1), ("L", 2)),
                           range(3, 8), DRAWER_HEIGHTS, (.8, 3.0), (.9, 2.0)))
    four_drawers = tuple(Configuration("L", depth, 2, "set", floor, rear, 2, 2)
                         for depth, floor, rear in product(range(3, 8), (.8, 3.0), (.9, 2.0)))
    return single_row + four_drawers


def representative_configurations():
    return (
        Configuration("S", 3, 1),
        Configuration("S", 4, 1, box_floor=3.0),
        Configuration("S", 4, 4),
        Configuration("L", 3, 4, drawer_columns=2),
        Configuration("M", 3, 2, module_rear=2.0),
        Configuration("L", 7, 2, box_floor=3.0, module_rear=2.0),
        Configuration("L", 3, 1, drawer_columns=2),
        Configuration("L", 6, 2, box_floor=3.0, module_rear=2.0, drawer_columns=2),
        Configuration("L", 6, 2, drawer_columns=2, drawer_rows=2),
    )


def configuration_label(configuration):
    layout = '²' if configuration.drawer_columns == 2 else ''
    if configuration.drawer_rows == 2:
        layout = ' (2×2 drawers)'
    return (f"{configuration.family}{configuration.depth_units}{layout} {configuration.height_units}F "
            f"floor={configuration.box_floor:g} rear={configuration.module_rear:g} "
            f"facade_floor={configuration.facade_floor} "
            f"box={configuration.box_variant} box_rear={configuration.box_rear_pattern} "
            f"pattern={configuration.wall_pattern}/{configuration.pattern_construction} "
            f"perimeters={configuration.wall_perimeters} nozzle={configuration.nozzle_size:g}")


def definition_report(pattern_settings=None):
    cases = []
    for configuration in all_configurations():
        if pattern_settings:
            configuration = replace(configuration, **pattern_settings)
        errors = definition_errors(configuration, assembly_definition(configuration))
        cases.append({"configuration": configuration.as_dict(), "passed": not errors,
                      "errors": errors})
    return {"case_count": len(cases), "passed": all(case["passed"] for case in cases),
            "cases": cases}


def parse_case(value):
    try:
        size, height, *thickness = value.split(":")
        size, *layout = size.replace('²', 'x2').lower().split('x')
        if len(layout) > 2:
            raise ValueError('Expected columns and optional rows')
        columns, rows = (list(map(int, layout)) + [1, 1])[:2]
        floor, rear = (map(float, thickness) if thickness else (.8, .9))
        return Configuration(size[0].upper(), int(size[1:]), int(height),
                             box_floor=floor, module_rear=rear,
                             drawer_columns=columns, drawer_rows=rows)
    except (ValueError, IndexError) as error:
        raise argparse.ArgumentTypeError(
            "Use S4:1, L6x2:2, or L6x2x2:2 (size[xcolumns[xrows]]:height[:floor:rear])") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--case", action="append", type=parse_case,
                      help="Size[xcolumns[xrows]]:height[:floor:rear], e.g. L6x2x2:2; repeatable")
    mode.add_argument("--all", action="store_true", help="Audit all 260 native assemblies")
    mode.add_argument("--representative", action="store_true", help="Audit the nine representative cases (default)")
    mode.add_argument("--definitions-only", action="store_true", help="Only check inexpensive scene inventory/placement")
    parser.add_argument("--output", type=Path, default=Path("research/assembly_fit.json"))
    parser.add_argument("--verbose", action="store_true", help="Print individual native pair progress")
    parser.add_argument('--box-variant', choices=('plain', 'gridfinity'), default='plain')
    parser.add_argument('--box-floor', type=float, choices=(0., .8, 3.),
                        help='Override the box floor for every case; 0 requires --box-variant gridfinity')
    parser.add_argument('--facade-floor', choices=('0.8', 'default'), default='default',
                        help='Use the shelled 0.8 mm facade or the original facade')
    parser.add_argument('--box-rear-pattern', choices=('plain', 'waffle', 'miura'), default='plain')
    parser.add_argument('--wall-pattern', choices=('plain', 'waffle', 'miura'), default='plain')
    parser.add_argument('--pattern-construction', choices=('recessed', 'corrugated'), default='recessed')
    parser.add_argument('--pattern-pitch', type=float, default=14.)
    parser.add_argument('--pattern-depth', type=float, default=1.7)
    parser.add_argument('--pattern-line-width', type=float, default=.65)
    parser.add_argument('--pattern-faces', choices=('all', 'sides'), default='all')
    parser.add_argument('--wall-perimeters', choices=('1', '2', 'full'),
                        help='Use the shared thin-wall mode; omission audits historical geometry')
    parser.add_argument('--nozzle-size', type=float, choices=(0.6, 0.8), default=0.6)
    args = parser.parse_args()
    pattern_settings = {key: getattr(args, key) for key in PATTERN_DEFAULTS}
    pattern_settings['wall_perimeters'] = (int(args.wall_perimeters) if args.wall_perimeters in ('1', '2')
                                          else args.wall_perimeters)
    pattern_settings['nozzle_size'] = args.nozzle_size
    pattern_settings['box_variant'] = args.box_variant
    pattern_settings['box_rear_pattern'] = args.box_rear_pattern
    pattern_settings['facade_floor'] = .8 if args.facade_floor == '0.8' else 'default'
    if args.box_floor is not None:
        pattern_settings['box_floor'] = args.box_floor
    try:
        Configuration(**pattern_settings)
    except ValueError as error:
        parser.error(str(error))
    configurations = ([] if args.definitions_only else args.case or
                      (all_configurations() if args.all else representative_configurations()))
    configurations = [replace(configuration, **pattern_settings) for configuration in configurations]
    definitions = definition_report(pattern_settings)
    cases = []
    for configuration in configurations:
        label = configuration_label(configuration)
        print(f"Checking {label}", flush=True)
        progress = (lambda message: print(f"  {message}", flush=True)) if args.verbose else None
        case = validate_assembly(configuration, progress=progress)
        cases.append(case)
        print(f"{label}: passed={case['passed']} ({case.get('elapsed_seconds', 0):.1f}s)", flush=True)
        for key in ("solids", "pairs", "mating"):
            for failure in case.get(key, []):
                if not failure["passed"]:
                    print(json.dumps(failure), flush=True)
    report = {
        "schema": "vault-assembly-fit/v1", "units": "mm",
        "method": "All supported scene inventories and proper rigid transforms; finished native "
                  "B-rep solids placed by vault.assembly, conservative separated-bounds "
                  "rejection followed by exact Boolean volume and minimum-distance checks "
                  "for every remaining unordered component pair. Independent source clearance "
                  "and contact expectations check mating registrations.",
        "volume_tolerance_mm3": VOLUME_TOLERANCE_MM3,
        "distance_tolerance_mm": DISTANCE_TOLERANCE_MM,
        "contact_rules": [{"kinds": sorted(kinds), "reason": reason}
                          for kinds, reason in CONTACT_RULES.items()],
        "definitions": definitions, "geometry_case_count": len(cases), "cases": cases,
        "limitations": "Closed rigid assembled pose only. Positive exploded-view offsets are "
                       "illustrative, not collision-certified paths. Module mouth webs and box "
                       "runner-channel sheets are removed; printing meshes retain them. "
                       "Accessory installation and fit are outside the native audit; accessories "
                       "are visible in the complete-set view. Screws are omitted. Geometry cases "
                       "are exactly those listed; definition coverage does not imply native "
                       "solid collision coverage for other configurations. No physical print-fit qualification.",
    }
    report["passed"] = definitions["passed"] and all(case["passed"] for case in cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Assembly audit: passed={report['passed']}; report={args.output}", flush=True)
    if not report["passed"]:
        raise SystemExit("Assembly geometry audit failed")


if __name__ == "__main__":
    main()
