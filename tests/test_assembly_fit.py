"""Collision/contact checks reject wrong geometry, including allowed mating pairs.

Full finished CAD cases are exercised by tools/check_assembly.py. These small
native solids give independent positive/negative controls for the same runtime
validator without rebuilding every printable component in the unit suite.
"""
from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from build123d import Box, Solid

from vault.assembly import assembly_definition
from vault.assembly_validation import (
    check_pair, definition_errors, validate_assembly, validation_signature,
)
from vault.generator import Configuration


class AssemblyFitTests(unittest.TestCase):
    def test_separated_bounds_certify_a_gap(self):
        shape = Box(2, 2, 2)
        result = check_pair({"id": "a", "kind": "module"}, shape,
                            {"id": "b", "kind": "box"}, shape.translate((3, 0, 0)))
        self.assertTrue(result["passed"])
        self.assertEqual(result["method"], "separated_bounds")
        self.assertAlmostEqual(result["minimum_gap_lower_bound_mm"], 1)

    def test_overlapping_bounds_do_not_imply_interfering_solids(self):
        cylinder = Solid.make_cylinder(1, 2)
        result = check_pair({"id": "a", "kind": "runner_guides"}, cylinder,
                            {"id": "b", "kind": "runner_slides"},
                            cylinder.translate((1.5, 1.5, 0)))
        self.assertTrue(result["passed"])
        self.assertEqual(result["method"], "native_intersection_and_distance")
        self.assertAlmostEqual(result["minimum_gap_mm"], math.sqrt(4.5) - 2)
        self.assertEqual(result["intersection_volume_mm3"], 0)

    def test_expected_contact_does_not_allow_positive_overlap(self):
        shape = Box(2, 2, 2)
        for kind in ("facade", "runner_slides", "runner_guides"):
            with self.subTest(kind=kind):
                result = check_pair({"id": "box", "kind": "box"}, shape,
                                    {"id": "other", "kind": kind}, shape.translate((1.5, 0, 0)))
                self.assertFalse(result["passed"])
                self.assertAlmostEqual(result["intersection_volume_mm3"], 2)

    def test_containment_is_a_collision_even_with_separate_surfaces(self):
        outer, inner = Box(10, 10, 10), Box(2, 2, 2)
        # Surface-distance alone reports 4 mm here and would miss this overlap.
        self.assertAlmostEqual(outer.distance_to(inner), 4)
        result = check_pair({"id": "module", "kind": "module"}, outer,
                            {"id": "box", "kind": "box"}, inner)
        self.assertFalse(result["passed"])
        self.assertAlmostEqual(result["intersection_volume_mm3"], 8)

    def test_only_explicit_mating_pairs_can_touch(self):
        shape = Box(2, 2, 2)
        for left, right, allowed in (("box", "facade", True), ("box", "runner_slides", True),
                                     ("facade", "runner_slides", True), ("module", "facade", True),
                                     ("box", "runner_guides", False), ("box", "rails", False),
                                     ("module", "runner_slides", False)):
            with self.subTest(left=left, right=right):
                result = check_pair({"id": "left", "kind": left}, shape,
                                    {"id": "right", "kind": right}, shape.translate((2, 0, 0)))
                self.assertEqual(result["passed"], allowed)
                self.assertAlmostEqual(result["minimum_gap_mm"], 0)
                self.assertEqual(result["intersection_volume_mm3"], 0)

    def test_invalid_or_partial_assembly_is_never_marked_passed(self):
        config = Configuration()
        definition = assembly_definition(config)
        invalid = deepcopy(definition)
        invalid["instances"] = invalid["instances"][:-1]
        self.assertTrue(definition_errors(config, invalid))
        with patch("vault.assembly_validation.assembly_definition", return_value=invalid), \
                patch("vault.assembly_validation.build_finished_components") as build:
            report = validate_assembly(config)
            self.assertFalse(report["passed"])
            build.assert_not_called()
        with self.assertRaisesRegex(ValueError, "Missing finished assembly components"):
            validate_assembly(config, {})

    def test_invalid_transforms_fail_before_native_geometry(self):
        config = Configuration()
        for index, value in ((0, -1), (0, 2), (3, 1), (12, float("nan"))):
            invalid = deepcopy(assembly_definition(config))
            invalid["instances"][0]["transform"][index] = value
            with self.subTest(index=index, value=value):
                self.assertTrue(definition_errors(config, invalid))

    def test_receipts_are_bound_to_configuration_placements_and_validator_source(self):
        config = Configuration()
        signature = validation_signature(config)
        self.assertEqual(signature, validation_signature(config))
        self.assertNotEqual(signature, validation_signature(Configuration(module_rear=2)))
        self.assertEqual(validation_signature(Configuration(box_floor=3, module_rear=2)),
                         validation_signature(Configuration(box_floor=3.0, module_rear=2.0)))
        changed = deepcopy(assembly_definition(config))
        changed["instances"][0]["transform"][12] = 1
        with patch("vault.assembly_validation.assembly_definition", return_value=changed):
            self.assertNotEqual(signature, validation_signature(config))
        with patch("vault.assembly_validation.Path.read_bytes", return_value=b"changed-validator"):
            self.assertNotEqual(signature, validation_signature(config))

    def test_supplied_finished_assets_are_checked_without_rebuilding(self):
        config = Configuration()
        # Wrong but individually valid assets: module and box overlap exactly.
        # This also exercises exported-report serialization and the validator's
        # component lookup/placement without constructing the real CAD models.
        shape = Box(2, 2, 2)
        components = {(instance["kind"], instance["component"]): shape
                      for instance in assembly_definition(config)["instances"]}
        with patch("vault.assembly_validation.build_finished_components") as build:
            report = validate_assembly(config, components)
            build.assert_not_called()
        self.assertFalse(report["passed"])
        self.assertEqual(len(report["pairs"]), 36)
        collision = next(pair for pair in report["pairs"] if pair["instances"] == ["module", "box"])
        self.assertFalse(collision["passed"])
        self.assertAlmostEqual(collision["intersection_volume_mm3"], 8)
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
