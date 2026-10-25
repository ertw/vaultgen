"""Audit the authoritative finished assembly with native solid geometry.

Run after sourcing .local-env::

    python tools/check_assembly.py --case S4:1
    python tools/check_assembly.py --representative
    python tools/check_assembly.py --all

The default representative sample covers every family, both heights, shortest
and longest catalog depths, and all four floor/rear thickness combinations.
``--all`` checks all 120 supported combinations and is intentionally expensive.
Every run also checks the inexpensive scene definitions for all 120 cases.
Exploded translations explain the parts; this audit certifies only the closed
assembled pose, not a continuous insertion, locking, or disassembly path.
"""

from __future__ import annotations

import argparse
from itertools import product
import json
from pathlib import Path

from vault.assembly import assembly_definition
from vault.assembly_validation import (
    CONTACT_RULES, DISTANCE_TOLERANCE_MM, VOLUME_TOLERANCE_MM3,
    definition_errors, validate_assembly,
)
from vault.generator import Configuration


def all_configurations():
    return tuple(Configuration(family, depth, height, "set", floor, rear)
                 for family, depth, height, floor, rear in product(
                     ("S", "M", "L"), range(3, 8), (1, 2), (.8, 3.0), (.9, 2.0)))


def representative_configurations():
    return (
        Configuration("S", 3, 1),
        Configuration("S", 4, 1, box_floor=3.0),
        Configuration("M", 3, 2, module_rear=2.0),
        Configuration("L", 7, 2, box_floor=3.0, module_rear=2.0),
    )


def configuration_label(configuration):
    return (f"{configuration.family}{configuration.depth_units} {configuration.height_units}F "
            f"floor={configuration.box_floor:g} rear={configuration.module_rear:g}")


def definition_report():
    cases = []
    for configuration in all_configurations():
        errors = definition_errors(configuration, assembly_definition(configuration))
        cases.append({"configuration": configuration.as_dict(), "passed": not errors,
                      "errors": errors})
    return {"case_count": len(cases), "passed": all(case["passed"] for case in cases),
            "cases": cases}


def parse_case(value):
    try:
        size, height, *thickness = value.split(":")
        floor, rear = (map(float, thickness) if thickness else (.8, .9))
        return Configuration(size[0].upper(), int(size[1:]), int(height),
                             box_floor=floor, module_rear=rear)
    except (ValueError, IndexError) as error:
        raise argparse.ArgumentTypeError("Use S4:1 or L7:2:3:2 (size:height:floor:rear)") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--case", action="append", type=parse_case,
                      help="Size:height[:floor:rear], e.g. S4:1 or L7:2:3:2; repeatable")
    mode.add_argument("--all", action="store_true", help="Audit all 120 native assemblies")
    mode.add_argument("--representative", action="store_true", help="Audit the four representative cases (default)")
    mode.add_argument("--definitions-only", action="store_true", help="Only check inexpensive scene inventory/placement")
    parser.add_argument("--output", type=Path, default=Path("research/assembly_fit.json"))
    parser.add_argument("--verbose", action="store_true", help="Print individual native pair progress")
    args = parser.parse_args()
    configurations = ([] if args.definitions_only else args.case or
                      (all_configurations() if args.all else representative_configurations()))
    definitions = definition_report()
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
                       "Lock, pinion, screws, and runner stoppers are omitted. Geometry cases "
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
