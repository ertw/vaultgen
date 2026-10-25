"""Compare every native guide with both supplied copies and check mating poses.

Run after sourcing .local-env. Temporary tessellation files are removed after
each run; only compact JSON evidence is retained in research/.
"""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build123d import Axis
import trimesh

from vault.reference import PROJECT_ROOT
from vault.runner_guides import RunnerGuideSpec, build_runner_guide
from vault.runner_slides import RunnerSlideSpec, build_runner_slide
from vault.shell import ShellDimensions, build_shell
from vault.tessellation import _tessellate
from vault.validation import _distance_target, _nearest, _surface_points


def overlap(a, b):
    common = a.intersect(b)
    return sum(item.volume for item in common) if common else 0.0


def stop_checks(guide, slide):
    """The source x4 head clears at 87 mm and meets the guide lip by 88 mm."""
    checks = []
    for travel, should_contact in ((87, False), (88, True)):
        placed = slide.translate((13.5, 25.8+travel, 4.8))
        volume, gap = overlap(guide, placed), guide.distance_to(placed)
        checks.append({
            "depth_units": 4, "travel_mm": travel, "expected_contact": should_contact,
            "intersection_volume_mm3": volume, "minimum_gap_mm": gap,
            "passed": volume > 1 if should_contact else volume < 1e-6 and gap > .049,
        })
    return checks


def main():
    sources = PROJECT_ROOT / "original_files/01. DRAWERS/07. Universal/Runners"
    reference = {
        "schema": "vault-runner-guides-reference/v1", "units": "mm",
        "method": "Bidirectional point-to-triangle distances on 5000 deterministic "
                  "area samples plus up to 5000 sampled mesh vertices in each direction, "
                  "with native chord tolerance 0.005 mm. Every supplied copy is checked; "
                  "no surfaces are excluded from sampling.",
        "distance_limit_mm": .025,
        "construction_sha256": hashlib.sha256(
            (PROJECT_ROOT / "src/vault/runner_guides.py").read_bytes()).hexdigest(),
        "parts": [],
    }
    fit = {
        "schema": "vault-runner-guides-fit/v1", "units": "mm",
        "method": "Native-solid intersections and exact minimum distances. Guide and slide "
                  "share print axes; seated slide translation is (13.5,25.8,4.8) mm. "
                  "S4 guide-to-module uses the source assembly registration, with module "
                  "sacrificial pocket supports disabled.",
        "slide_poses": [], "module_poses": [], "stop_poses": [],
        "limitations": "Preserves the supplied tight 0.0498 mm stem-side clearance. "
                      "These geometric checks do not qualify physical printer fit. "
                      "The separately supplied runner stopper is not included in this audit.",
    }
    guides = {}
    with TemporaryDirectory(prefix="vault-guide-audit-") as directory:
        for depth in range(3, 8):
            guide = build_runner_guide(spec=RunnerGuideSpec(depth))
            guides[depth] = guide
            destination = Path(directory) / "guide.stl"
            mesh = _tessellate(guide, destination, deflection=.005)
            native_points = _surface_points(mesh, 5000, seed=2002)
            native_target = _distance_target(mesh)
            source_path = sources / f"x{depth} Runner Guides.stl"
            originals = sorted(trimesh.load_mesh(source_path).split(),
                               key=lambda part: part.bounds[0, 0])
            for index, original in enumerate(originals):
                origin = original.bounds[0].copy()
                original.vertices -= origin
                forward, _ = _nearest(native_target, _surface_points(original, 5000, seed=1001))
                reverse, _ = _nearest(_distance_target(original), native_points)
                item = {
                    "depth_units": depth, "copy": index+1,
                    "source": str(source_path.relative_to(PROJECT_ROOT)),
                    "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                    "source_subtract_origin_mm": origin.tolist(),
                    "source_volume_mm3": float(original.volume),
                    "native_volume_mm3": float(guide.volume),
                    "source_to_native_max_mm": float(forward.max()),
                    "native_to_source_max_mm": float(reverse.max()),
                    "passed": bool(max(forward.max(), reverse.max()) < .025),
                }
                reference["parts"].append(item)
                print(f"x{depth} copy {index+1}: "
                      f"{max(forward.max(), reverse.max()):.5f} mm maximum deviation", flush=True)
            destination.unlink()
            slide = build_runner_slide(spec=RunnerSlideSpec(depth))
            for travel in (0, 10, 40):
                placed = slide.translate((13.5, 25.8+travel, 4.8))
                volume, gap = overlap(guide, placed), guide.distance_to(placed)
                fit["slide_poses"].append({
                    "depth_units": depth, "travel_mm": travel,
                    "intersection_volume_mm3": volume, "minimum_gap_mm": gap,
                    "passed": volume < 1e-6 and gap > .049,
                })
    module = build_shell(dimensions=replace(ShellDimensions(), pocket_support_thickness=0))
    for side in (-1, 1):
        guide = guides[4].rotate(Axis.Y, -side*90).translate((side*78.7, 2.3, 23.5-side*13.5))
        volume, gap = overlap(module, guide), module.distance_to(guide)
        fit["module_poses"].append({
            "family": "S", "depth_units": 4, "height_units": 1, "side": side,
            "rotation_y_degrees": -side*90,
            "translation_mm": [side*78.7, 2.3, 23.5-side*13.5],
            "intersection_volume_mm3": volume, "minimum_gap_mm": gap,
            "passed": volume < 1e-6 and gap > .1,
        })
    fit["stop_poses"] = stop_checks(guides[4], build_runner_slide())
    reference["passed"] = all(p["passed"] for p in reference["parts"])
    fit["passed"] = all(p["passed"] for key in ("slide_poses", "module_poses", "stop_poses")
                        for p in fit[key])
    for name, report in (("runner_guides_reference", reference), ("runner_guides_fit", fit)):
        destination = PROJECT_ROOT / "research" / f"{name}.json"
        destination.write_text(json.dumps(report, indent=2)+"\n")
        print(f"{name}: passed={report['passed']}", flush=True)
    if not reference["passed"] or not fit["passed"]:
        raise SystemExit("Runner guide audit failed")


if __name__ == "__main__":
    main()
