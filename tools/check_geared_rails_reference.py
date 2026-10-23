"""Compare both native S rails with the complete original STL surfaces.

Run after sourcing .local-env. Source loading lives exclusively in this
measurement tool, never in the native builders. No surfaces are excluded.
"""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh

from vault.geared_rails import D, build_gear_rail
from vault.reference import PROJECT_ROOT
from vault.tessellation import _tessellate
from vault.validation import _distance_target, _nearest, _surface_points, _summary


SOURCE = PROJECT_ROOT / "original_files/01. DRAWERS/07. Universal/Geared Rails/S Rails.stl"


def main():
    source = trimesh.load_mesh(SOURCE)
    components = sorted(source.split(), key=lambda part: part.bounds[0, 1])
    output = PROJECT_ROOT / "out/reviews/geared-rails-reference"
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "vault-geared-rails-reference-audit/v1",
        "units": "mm",
        "source": str(SOURCE.relative_to(PROJECT_ROOT)),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "construction_sha256": hashlib.sha256((PROJECT_ROOT / "src/vault/geared_rails.py").read_bytes()).hexdigest(),
        "dimensions": asdict(D),
        "method": "Bidirectional exact point-to-triangle distances. Each direction uses 20000 "
                  "deterministic area-weighted samples plus source/native mesh vertices. "
                  "Native tessellation absolute chord tolerance is 0.0025 mm. No surfaces excluded.",
        "distance_limit_mm": .1,
        "limitations": "Sampled surface agreement, not a proven Hausdorff bound. Native geometry "
                       "regularizes tiny source ripples and rounded rib-end intersections. "
                       "This audit does not test assembled fit, tooth motion, or a physical print.",
        "parts": [],
    }
    # The common X/Z origins are direct source coordinates. Each Y origin is
    # the straight unfeatured back side, not the retained rail's rib extent.
    for retained, original, y_origin in zip((True, False), components, (2056.76123046875, 2062.648681640625)):
        name = "retained" if retained else "plain"
        origin = np.array([8941.02734375, y_origin, 38.43763732910156])
        original.vertices -= origin
        native = build_gear_rail(retained)
        mesh = _tessellate(native, output / f"{name}-comparison.stl", deflection=.0025)
        originals = _surface_points(original, 20_000, seed=1001)
        models = _surface_points(mesh, 20_000, seed=2002)
        distances, closest = _nearest(_distance_target(mesh), originals)
        reverse, reverse_closest = _nearest(_distance_target(original), models)
        item = {
            "name": name,
            "source_subtract_origin_mm": origin.tolist(),
            "source_volume_mm3": float(original.volume),
            "native_volume_mm3": float(native.volume),
            "relative_volume_error": float((native.volume - original.volume) / original.volume),
            "source_to_native": _summary(originals, distances, closest, .1),
            "native_to_source": _summary(models, reverse, reverse_closest, .1),
            "passed": bool(distances.max() <= .1 and reverse.max() <= .1),
        }
        report["parts"].append(item)
        print(name, "max distances mm", distances.max(), reverse.max(), flush=True)
    report["passed"] = all(part["passed"] for part in report["parts"])
    destination = PROJECT_ROOT / "research/geared_rails_reference.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "report": str(destination)}))
    if not report["passed"]:
        raise SystemExit("Gear rail reference audit failed")


if __name__ == "__main__":
    main()
