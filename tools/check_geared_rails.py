"""Certify complete S-rail translation sweeps with conservative native solids.

The source assembly manual p4 shows lateral rail insertion into the box before
inserting the drawer into its module. These are distinct paths: 134 mm lateral
insertion without the module, then 0..20 mm opposed locking travel in the module.

Swept envelopes retain the real octagonal cross section. They fill tooth valleys,
round ends, retaining-rib ramps, and the tail's thickness ramp, so every real rail
position lies inside the envelope. A positive distance of an envelope therefore
certifies the entire continuous translation, not merely sampled positions.
"""
from dataclasses import replace
import hashlib
import json
from math import sqrt
from pathlib import Path

from build123d import Axis, Compound, Edge, Face, Solid, Wire, export_step
from vault.box import build_box
from vault.geared_rails import D, build_gear_rail
from vault.reference import PROJECT_ROOT
from vault.shell import ShellDimensions, build_shell

RAIL_SOURCE = PROJECT_ROOT / "original_files/01. DRAWERS/07. Universal/Geared Rails/S Rails.stl"
INSERTION_TRAVEL = 134.0
LOCKING_TRAVEL = 20.0
# The analytic three-point tail arc extends 0.00003 mm beyond the nominal
# length datum. This conservative allowance also covers OCC trimming tolerance.
END_BOUND_ALLOWANCE = .0001


def place_gear_rail(part, upper, travel=0):
    """Proper rotations: upper teeth face down, lower teeth up; rib belongs above.

    A 0.2 mm end gap locates the rounded end of the retracted rail relative to
    the closed box pocket at X=±66.3. Positive travel moves both tips outward.
    """
    part = part.rotate(Axis.X, -90)
    if not upper:
        part = part.rotate(Axis.Y, 180)
    return part.translate((-66.1 + travel if upper else 66.1 - travel,
                           183.1, 40.193 if upper else 6.807))


def _body_section(x, capped_width=None):
    b, w, h = D.edge_bevel, D.width, D.thickness
    if capped_width is None:
        points = [(b, 0), (w-b, 0), (w, b), (w, h-b),
                  (w-b, h), (b, h), (0, h-b), (0, b)]
    else:
        # The tail cap lies inside both tooth-side bevels, so it ends at the
        # original flat top and bottom; only the back bevels remain.
        if not b < capped_width < w-b:
            raise ValueError("Expected tail cap inside the flat thickness section")
        points = [(b, 0), (capped_width, 0), (capped_width, h),
                  (b, h), (0, h-b), (0, b)]
    return Face(Wire.make_polygon([(x, y, z) for y, z in points]))


def _rib_envelope(x, length):
    """Constant maximum rib section, including its native R0.8 outer corners."""
    p, r, b, h = D.retaining_projection, D.retaining_radius, D.edge_bevel, D.thickness
    low, high, center, diagonal = b-.0078, h-b+.0078, -p+r, r/sqrt(2)
    q = lambda y, z: (x, y, z)
    edges = [
        Edge.make_line(q(.02, low), q(center, low)),
        Edge.make_three_point_arc(q(center, low), q(center-diagonal, low+r-diagonal), q(-p, low+r)),
        Edge.make_line(q(-p, low+r), q(-p, high-r)),
        Edge.make_three_point_arc(q(-p, high-r), q(center-diagonal, high-r+diagonal), q(center, high)),
        Edge.make_line(q(center, high), q(.02, high)),
        Edge.make_line(q(.02, high), q(.02, low)),
    ]
    return Solid.extrude(Face(Wire(edges)), (length, 0, 0))


def swept_rail_envelope(upper, travel, limited_tail=False):
    """Conservative solid containing all rail poses from travel zero to `travel`.

    The full-height section ends only after the final flank reaches tail_width;
    every later point is at or below tail_width. Translating this station by the
    maximum travel bounds all intermediate positions. The subsequent constant
    tail cap intentionally fills the final root, rounded tip, and thickness ramp.
    """
    if travel < 0:
        raise ValueError("Travel must be nonnegative")
    if limited_tail:
        width = D.valley_width - D.narrow_valley_reduction * (D.tooth_count-1 in D.narrow_valleys)
        left = D.valley_centers[-1] - width/2
        root_center_y = D.root_floor + D.root_radius
        tail_start = left + D.root_radius - sqrt(D.root_radius**2 - (D.tail_width-root_center_y)**2)
        length = tail_start + travel
        body = Solid.extrude(_body_section(0), (length, 0, 0)).fuse(
            Solid.extrude(_body_section(length, D.tail_width),
                          (D.length+END_BOUND_ALLOWANCE+travel-length, 0, 0)))
    else:
        body = Solid.extrude(_body_section(0), (D.length+END_BOUND_ALLOWANCE+travel, 0, 0))
    if upper:
        body = body.fuse(_rib_envelope(D.retaining_start,
                                     D.retaining_end-D.retaining_start+travel))
    return place_gear_rail(body.clean(), upper)


def distance_record(moving, fixed):
    distance, near, far = moving.distance_to_with_closest_points(fixed)
    return {"minimum_distance_mm": distance,
            "moving_point_mm": list(near), "fixed_point_mm": list(far)}


def common_volume(a, b):
    common = a.intersect(b)
    return 0.0 if common is None else sum(s.volume for s in common.solids())


def main():
    out = PROJECT_ROOT / "out/reviews/geared-rail-fit"
    out.mkdir(parents=True, exist_ok=True)
    module = build_shell(dimensions=replace(ShellDimensions(), pocket_support_thickness=0))
    boxes = {"standard": build_box()}
    rails = {"upper_retained": build_gear_rail(True), "lower_plain": build_gear_rail(False)}
    sweeps, poses, stops, containment = [], [], [], []
    for name, rail in rails.items():
        upper = name == "upper_retained"
        insertion = swept_rail_envelope(upper, INSERTION_TRAVEL)
        locking = swept_rail_envelope(upper, LOCKING_TRAVEL, limited_tail=True)
        for variant, box in boxes.items():
            result = {"rail": name, "target": variant+"_box", "path": "lateral_insertion",
                      "travel_mm": [0, INSERTION_TRAVEL], "continuous": True,
                      **distance_record(insertion, box)}
            sweeps.append(result)
            print(json.dumps(result), flush=True)
        result = {"rail": name, "target": "finished_module", "path": "locking",
                  "travel_mm": [0, LOCKING_TRAVEL], "continuous": True,
                  **distance_record(locking, module)}
        sweeps.append(result)
        print(json.dumps(result), flush=True)
        for travel in (0, LOCKING_TRAVEL):
            placed = place_gear_rail(rail, upper, travel)
            for target, fixed in (("standard_box", boxes["standard"]), ("finished_module", module)):
                result = {"rail": name, "target": target, "travel_mm": travel,
                          **distance_record(placed, fixed)}
                poses.append(result)
                print(json.dumps(result), flush=True)
            # A separate exact Boolean checks the implemented bounds against
            # the native rail at both sweep endpoints, including the tip.
            outside = placed.cut(locking)
            outside_volume = 0.0 if outside is None else sum(s.volume for s in outside.solids())
            containment.append({"rail": name, "travel_mm": travel,
                                "rail_volume_outside_envelope_mm3": outside_volume})
        stop_rail = place_gear_rail(rail, upper, 21)
        stops.append({"rail": name, "travel_mm": 21,
                      "overlap_volume_mm3": common_volume(stop_rail, module),
                      "meaning": "Beyond qualified locking travel; module stop interference is intentional."})
    locked = [place_gear_rail(rail, name == "upper_retained", LOCKING_TRAVEL)
              for name, rail in rails.items()]
    assembly_path = out / "box_with_locked_rails.step"
    module_path = out / "module_with_locked_rails.step"
    export_step(Compound(label="S4 box and geared rails at 20 mm travel",
                         children=[boxes["standard"], *locked]), assembly_path)
    export_step(Compound(label="S4 finished sleeve and geared rails at 20 mm travel",
                         children=[module, *locked]), module_path)
    construction = ("src/vault/geared_rails.py", "src/vault/box.py", "src/vault/shell.py",
                    "tools/check_geared_rails.py")
    report = {
        "schema": "vault-geared-rail-clearance/v1", "units": "mm",
        "source": {"path": str(RAIL_SOURCE.relative_to(PROJECT_ROOT)),
                   "sha256": hashlib.sha256(RAIL_SOURCE.read_bytes()).hexdigest(),
                   "assembly_reference": "original_files/02_Drawer Assembly.pdf, page 4"},
        "construction_sha256": {path: hashlib.sha256((PROJECT_ROOT/path).read_bytes()).hexdigest()
                                for path in construction},
        "placement": {
            "upper": {"rotation_matrix": [[1, 0, 0], [0, 0, 1], [0, -1, 0]],
                      "translation_at_zero_mm": [-66.1, 183.1, 40.193], "travel_axis": [1, 0, 0]},
            "lower": {"rotation_matrix": [[-1, 0, 0], [0, 0, 1], [0, 1, 0]],
                      "translation_at_zero_mm": [66.1, 183.1, 6.807], "travel_axis": [-1, 0, 0]},
            "explanation": "Both rotations have determinant +1. Retaining rib is above the upper rail. "
                           "The retracted rounded ends have 0.2 mm axial clearance to closed box pockets."},
        "module_pocket_support_thickness_mm": 0,
        "swept_envelope_end_allowance_mm": END_BOUND_ALLOWANCE,
        "continuous_sweeps": sweeps, "actual_rail_poses": poses,
        "envelope_containment_checks": containment, "overtravel_positive_controls": stops,
        "method": "Native B-rep minimum distance against conservative swept solids. Full body octagon "
                  "fills tooth valleys; maximum rib section fills its ramps. For locking, the full-width "
                  "section ends after the final flank crosses tail_width; a constant tail fills the "
                  "root, tip round and thickness ramp. Therefore every intermediate translated rail "
                  "is contained, and positive envelope distances certify continuous clearance.",
        "review_step": [str(assembly_path.relative_to(PROJECT_ROOT)), str(module_path.relative_to(PROJECT_ROOT))],
        "limitations": "Rigid CAD fit only; no physical print qualification, deformation, or drive-pinion "
                       "meshing test. Remove module pocket supports before operation. Rails install "
                       "laterally into the box before the drawer enters the sleeve. 21 mm travel "
                       "intentionally reaches the module stop; qualified locking travel is 0..20 mm.",
    }
    report["passed"] = (all(r["minimum_distance_mm"] > .18 for r in sweeps)
                        and all(r["minimum_distance_mm"] > .19 for r in poses)
                        and all(r["rail_volume_outside_envelope_mm3"] < 1e-5 for r in containment)
                        and all(r["overlap_volume_mm3"] > .01 for r in stops))
    payload = json.dumps(report, indent=2)+"\n"
    (out/"clearance.json").write_text(payload)
    (PROJECT_ROOT/"research/geared_rail_fit.json").write_text(payload)
    print(json.dumps({"passed": report["passed"], "report": str(out/"clearance.json")}), flush=True)
    if not report["passed"]:
        raise SystemExit("Geared rail clearance audit failed")


if __name__ == "__main__":
    main()
