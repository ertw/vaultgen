"""Native geometry checks shared by generation and the assembly audit CLI.

Validate only the closed assembled pose. Explosion vectors are illustrative
translations, not certified paths; omitted hardware is not represented.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
from itertools import combinations, product
import json
import math
from pathlib import Path
import time

from .assembly import apply_transform, assembly_definition, build_finished_components


VOLUME_TOLERANCE_MM3 = 1e-5
DISTANCE_TOLERANCE_MM = 1e-6

# Seating planes and a fully inserted slide's rear stop intentionally touch.
# These rules allow zero *distance*, never a positive intersection volume.
CONTACT_RULES = {
    frozenset(("module", "facade")): "Facade seats on the module's front lands",
    frozenset(("box", "facade")): "Facade seats on the box's front attachment lands",
    frozenset(("box", "runner_slides")): "Fully inserted slide touches its box rear stop",
    frozenset(("facade", "runner_slides")): "Slide's front end is flush with the facade seating plane",
}


def validation_signature(configuration):
    """Bind a saved pass to these scene placements and this validator revision.

    This helper deliberately imports no CAD kernel so the web API can check
    validation receipts without running a geometry worker.
    """
    # JSON job bodies commonly contain 3/2 while URL parameters are parsed as
    # 3.0/2.0. They describe the same geometry and must share a receipt key.
    normalized = replace(configuration, box_floor=float(configuration.box_floor),
                         module_rear=float(configuration.module_rear))
    payload = {"definition": assembly_definition(normalized),
               "validator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def definition_errors(configuration, definition):
    """Check inventory and rigid placement for every supported scene variant."""
    errors = []
    instances = definition.get("instances", [])
    counts = Counter(instance.get("kind") for instance in instances)
    drawer_count = configuration.drawer_count
    per_bay = {"box": 1, "facade": 1, "rails": 2,
               "runner_guides": configuration.drawer_height_units * 2,
               "runner_slides": configuration.drawer_height_units * 2}
    expected = {"module": 1, **{kind: count * drawer_count for kind, count in per_bay.items()}}
    if counts != expected:
        errors.append(f"Wrong instance inventory: {dict(counts)!r}; expected {expected!r}")
    if len({instance.get("id") for instance in instances}) != len(instances):
        errors.append("Instance IDs are not unique")
    bay_counts = Counter((instance.get("bay", 1), instance.get("kind"))
                         for instance in instances if instance.get("kind") != "module")
    expected_bays = Counter({(bay, kind): count for bay in range(1, drawer_count + 1)
                            for kind, count in per_bay.items()})
    if bay_counts != expected_bays:
        errors.append("Each drawer bay must have its own complete component inventory")
    for instance in instances:
        matrix = instance.get("transform", [])
        name = instance.get("id", "unnamed")
        if len(matrix) != 16 or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                        for value in matrix):
            errors.append(f"{name}: invalid 4×4 transform")
            continue
        if any(abs(matrix[index] - expected) > 1e-9
               for index, expected in ((3, 0), (7, 0), (11, 0), (15, 1))):
            errors.append(f"{name}: transform is not affine")
        columns = [matrix[index:index + 3] for index in (0, 4, 8)]
        for left in range(3):
            for right in range(3):
                dot = sum(a * b for a, b in zip(columns[left], columns[right]))
                if abs(dot - (left == right)) > 1e-9:
                    errors.append(f"{name}: transform scales or shears geometry")
                    break
        a, b, c = columns
        determinant = (a[0] * (b[1] * c[2] - b[2] * c[1])
                       - b[0] * (a[1] * c[2] - a[2] * c[1])
                       + c[0] * (a[1] * b[2] - a[2] * b[1]))
        if abs(determinant - 1) > 1e-9:
            errors.append(f"{name}: transform mirrors mesh winding")
        explosion = instance.get("explode", [])
        if len(explosion) != 3 or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                          for value in explosion):
            errors.append(f"{name}: invalid explosion translation")
    for kind in ("runner_guides", "runner_slides"):
        actual = Counter((instance.get("bay", 1), instance.get("side"), instance.get("tier"))
                         for instance in instances if instance.get("kind") == kind)
        expected = Counter(product(range(1, drawer_count + 1), (-1, 1),
                                   range(1, configuration.drawer_height_units + 1)))
        if actual != expected:
            errors.append(f"{kind}: expected one left/right pair per populated tier in each bay")
    return errors


def bounds_gap(left, right):
    """Conservative lower bound on separation of two axis-aligned boxes."""
    a, b = left.bounding_box(), right.bounding_box()
    return math.sqrt(sum(max(0, low_b - high_a, low_a - high_b) ** 2
                         for low_a, high_a, low_b, high_b in
                         zip(a.min, a.max, b.min, b.max)))


def intersection_volume(left, right):
    common = left.intersect(right)
    return 0.0 if common is None else sum(abs(solid.volume) for solid in common.solids())


def check_pair(left_instance, left, right_instance, right):
    """No pair is exempt from the positive-volume collision check."""
    rule = CONTACT_RULES.get(frozenset((left_instance["kind"], right_instance["kind"])))
    if (left_instance["kind"] != "module" and right_instance["kind"] != "module"
            and left_instance.get("bay", 1) != right_instance.get("bay", 1)):
        rule = None
    lower_bound = bounds_gap(left, right)
    result = {"instances": [left_instance["id"], right_instance["id"]],
              "contact_rule": rule, "bounds_gap_mm": lower_bound}
    if lower_bound > DISTANCE_TOLERANCE_MM:
        result.update(method="separated_bounds", intersection_volume_mm3=0.0,
                      minimum_gap_lower_bound_mm=lower_bound, passed=True)
        return result
    volume = intersection_volume(left, right)
    gap = left.distance_to(right)
    result.update(method="native_intersection_and_distance", intersection_volume_mm3=volume,
                  minimum_gap_mm=gap,
                  passed=volume <= VOLUME_TOLERANCE_MM3 and
                         (rule is not None or gap > DISTANCE_TOLERANCE_MM))
    return result


def mating_checks(configuration, placed, pair_results=()):
    """Source-established clearances catch misplaced parts that merely miss."""
    checks = []
    pair_distances = {frozenset(pair["instances"]): pair["minimum_gap_mm"]
                      for pair in pair_results if "minimum_gap_mm" in pair}
    module = next((instance, shape) for instance, shape in placed if instance["kind"] == "module")
    drawers = {(instance.get("bay", 1), instance["kind"]): (instance, shape)
               for instance, shape in placed if instance["kind"] in ("box", "facade")}

    def distance(left_instance, left, right_instance, right):
        cached = pair_distances.get(frozenset((left_instance["id"], right_instance["id"])))
        return left.distance_to(right) if cached is None else cached

    for instance, shape in placed:
        kind = instance["kind"]
        targets = []
        if kind == "runner_guides":
            targets = [("module", .1, None)]
        elif kind == "rails":
            targets = [("box", .19, None), ("module", .08, None)]
        elif kind == "runner_slides":
            targets = [("box", None, DISTANCE_TOLERANCE_MM)]
            guide_instance, guide = next((other, shape) for other, shape in placed
                         if other["kind"] == "runner_guides"
                         and other.get("bay", 1) == instance.get("bay", 1)
                         and other["side"] == instance["side"]
                         and other["tier"] == instance["tier"])
            gap = distance(instance, shape, guide_instance, guide)
            checks.append({"instance": instance["id"], "target": "matching_runner_guide",
                           "minimum_gap_mm": gap, "expected_gap_mm": [.049, .051],
                           "passed": .049 < gap < .051})
        for target, minimum, maximum in targets:
            target_instance, target_shape = (module if target == "module" else
                                             drawers[instance.get("bay", 1), target])
            gap = distance(instance, shape, target_instance, target_shape)
            checks.append({"instance": instance["id"], "target": target,
                           "minimum_gap_mm": gap, "expected_min_mm": minimum,
                           "expected_max_mm": maximum,
                           "passed": (minimum is None or gap > minimum)
                                     and (maximum is None or gap <= maximum)})
    for bay in range(1, configuration.drawer_count + 1):
        facade_instance, facade_shape = drawers[bay, "facade"]
        for kind in ("module", "box"):
            instance, shape = module if kind == "module" else drawers[bay, kind]
            gap = distance(instance, shape, facade_instance, facade_shape)
            checks.append({"instance": facade_instance["id"], "target": kind,
                           "minimum_gap_mm": gap, "expected_max_mm": DISTANCE_TOLERANCE_MM,
                           "passed": gap <= DISTANCE_TOLERANCE_MM})
    return checks


def validate_assembly(configuration, components=None, *, progress=None):
    """Return a JSON-safe audit of this scene and these exact finished shapes.

    ``components`` maps (kind, component) to native-coordinate finished solids.
    A caller validating an exported build should pass solids imported from its
    immutable native STEP assets, so the audit certifies the viewed geometry.
    The report fails on invalid transforms, invalid solids, any positive-volume
    interference above numeric tolerance, unintended touching, or lost mating
    registrations. Missing components raise ValueError rather than passing a
    partial assembly.
    """
    started = time.monotonic()
    definition = assembly_definition(configuration)
    errors = definition_errors(configuration, definition)
    if errors:
        return {"configuration": configuration.as_dict(), "definition_errors": errors,
                "passed": False}
    if progress:
        progress("building finished native components" if components is None
                 else "validating supplied finished native components")
    native = build_finished_components(configuration) if components is None else components
    missing = {(instance["kind"], instance["component"]) for instance in definition["instances"]} - set(native)
    if missing:
        raise ValueError(f"Missing finished assembly components: {sorted(missing)!r}")
    placed = [(instance, apply_transform(native[(instance["kind"], instance["component"])],
                                         instance["transform"]))
              for instance in definition["instances"]]
    solids = []
    for instance, shape in placed:
        original = native[(instance["kind"], instance["component"])]
        record = {"instance": instance["id"], "valid": shape.is_valid,
                  "solid_count": len(shape.solids()), "volume_mm3": shape.volume,
                  "placement_volume_error_mm3": abs(shape.volume - original.volume)}
        record["passed"] = (record["valid"] and record["solid_count"] == 1
                            and record["volume_mm3"] > 0
                            and record["placement_volume_error_mm3"] < VOLUME_TOLERANCE_MM3)
        solids.append(record)
    pairs = []
    for (left_instance, left), (right_instance, right) in combinations(placed, 2):
        if progress:
            progress(f"checking {left_instance['id']} / {right_instance['id']}")
        pairs.append(check_pair(left_instance, left, right_instance, right))
    mating = mating_checks(configuration, placed, pairs)
    return {"configuration": configuration.as_dict(), "elapsed_seconds": time.monotonic() - started,
            "definition_errors": errors, "solids": solids, "pairs": pairs, "mating": mating,
            "passed": all(record["passed"] for record in [*solids, *pairs, *mating])}


