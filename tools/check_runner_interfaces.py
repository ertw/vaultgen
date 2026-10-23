"""Check handed runner interfaces against physically rotated purchased sources.

The historical module comparison swaps Y and Z, which reflects the module.
Assembly checks instead use (-X, Z, Y), a proper rotation with determinant +1.
Run after sourcing .local-env. The JSON report records exact source section
crossings and native solid occupancy; the figure shows actual section contours.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh

from build123d import Plane
from vault.box import build_box
from vault.reference import PROJECT_ROOT, SOURCE, SOURCE_ORIGIN
from vault.shell import ShellDimensions, build_shell


SECTION_Y = 185.5
BOX_SOURCE = PROJECT_ROOT / "original_files/01. DRAWERS/01. S Families/S4/Boxes/S4 Box 1F.stl"
BOX_ORIGIN = np.array([9001.5546875, 1167.24138, 1.0])
MODULE_ROTATION = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]])
HISTORICAL_MODULE_MAP = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]])


def source_meshes():
    module = trimesh.load_mesh(SOURCE)
    # Subtract the datum in the original axes before applying a proper rotation.
    original_origin = SOURCE_ORIGIN[[0, 2, 1]]
    module.vertices = (module.vertices - original_origin) @ MODULE_ROTATION.T
    box = trimesh.load_mesh(BOX_SOURCE)
    box.vertices -= BOX_ORIGIN
    return {"module": module, "box": box}


def source_section(mesh, y):
    return trimesh.intersections.mesh_plane(mesh, [0, 1, 0], [0, y, 0])[:, :, [0, 2]]


def vertical_crossings(segments, x):
    """Intersect one XZ contour with a vertical ray, preserving all Z crossings."""
    dx = segments[:, 1, 0] - segments[:, 0, 0]
    crossing = (((segments[:, 0, 0] < x) & (segments[:, 1, 0] > x))
                | ((segments[:, 0, 0] > x) & (segments[:, 1, 0] < x)))
    chosen = segments[crossing & (np.abs(dx) > 1e-10)]
    fraction = (x - chosen[:, 0, 0]) / (chosen[:, 1, 0] - chosen[:, 0, 0])
    heights = chosen[:, 0, 1] + fraction * (chosen[:, 1, 1] - chosen[:, 0, 1])
    # Joining triangles can emit coincident intersections. This precision is
    # tighter than the source binary STL's coordinate quantization.
    return np.unique(np.round(heights, 6)).tolist()


def native_section(shape, y):
    """Sample exact native section edges for plotting; occupancy stays analytic."""
    pieces = shape.intersect(Plane(origin=(0, y, 0), z_dir=(0, 1, 0)))
    segments = []
    for piece in pieces:
        for edge in piece.edges():
            count = max(2, int(np.ceil(edge.length / .04)) + 1)
            points = np.array([[p.X, p.Z] for p in
                               (edge.position_at(t) for t in np.linspace(0, 1, count))])
            segments.extend(np.stack((points[:-1], points[1:]), axis=1))
    return np.asarray(segments)


def figure(source_sections, native_sections, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D

    colors = {"module": "#bd650b", "box": "#167da7"}
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.4), sharex="col", sharey="col")
    panels = [((-79, -61), (4, 14), "−X: lower gear exit and female pocket", -66.8, -70.3344, 8),
              ((61, 79), (33, 43), "+X: upper gear exit and female pocket", 66.8, 70.3344, 39)]
    for row, (sections, label) in enumerate([(source_sections, "Originals, proper rotation"),
                                             (native_sections, "Native CAD, module support off")]):
        for column, (xlim, zlim, title, box_x, module_x, z) in enumerate(panels):
            ax = axes[row, column]
            for name in ("box", "module"):
                ax.add_collection(LineCollection(sections[name], colors=colors[name], linewidths=1.4))
            ax.scatter([box_x, module_x], [z, z], c=[colors["box"], colors["module"]],
                       marker="x", s=40, zorder=5)
            ax.set_xlim(*xlim)
            ax.set_ylim(*zlim)
            ax.set_aspect("equal", adjustable="box")
            ax.grid(alpha=.18)
            if row == 0:
                ax.set_title(title, fontsize=11)
            else:
                ax.set_xlabel("Assembly X (mm)")
            ax.set_ylabel("Assembly Z (mm)")
            ax.text(.02, .96, label, transform=ax.transAxes, va="top", fontsize=9,
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": .9})
    fig.suptitle(f"S4 1F runner interfaces — actual sections at Y = {SECTION_Y:g} mm", fontsize=14)
    fig.legend([Line2D([0], [0], color=colors[name], lw=2) for name in ("box", "module")],
               ["Drawer box", "Module sleeve"], loc="lower center", bbox_to_anchor=(.5, .05), ncol=2)
    fig.text(.5, .02, "× marks checked clearance points. Module source uses (−X, Z, Y), determinant +1. "
             "Source blends and simplified native box recesses differ.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, .1, 1, .95), h_pad=2)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def main():
    source = source_meshes()
    source_sections = {name: source_section(mesh, SECTION_Y) for name, mesh in source.items()}
    native = {"module": build_shell(dimensions=replace(ShellDimensions(), pocket_support_thickness=0)),
              "box": build_box()}
    probes = []
    for name, absolute_x in (("module", 70.3344), ("box", 66.8)):
        for sign in (-1, 1):
            x = sign * absolute_x
            crossings = vertical_crossings(source_sections[name], x)
            if len(crossings) % 2:
                raise ValueError(f"Odd source crossing count for {name} at X={x}: {crossings}")
            for z in (8., 39.):
                expected_material = (sign > 0 and z == 8) or (sign < 0 and z == 39)
                source_material = sum(height < z for height in crossings) % 2 == 1
                native_material = bool(native[name].is_inside((x, SECTION_Y, z)))
                probes.append({"component": name, "point_mm": [x, SECTION_Y, z],
                               "expected_material": expected_material,
                               "source_material": source_material, "native_material": native_material,
                               "source_vertical_crossings_z_mm": crossings,
                               "passed": source_material == native_material == expected_material})
    output_dir = PROJECT_ROOT / "out/reviews/runner-interfaces"
    image_path = output_dir / "sections.png"
    native_sections = {name: native_section(shape, SECTION_Y) for name, shape in native.items()}
    figure(source_sections, native_sections, image_path)
    report = {
        "schema": "vault-runner-interface-audit/v1", "units": "mm",
        "method": "Exact original-STL plane intersections and analytic native-CAD occupancy. "
                  "Eight probes check intended clearances and retained opposite-side material. "
                  "Module sacrificial supports are disabled for mating checks.",
        "source_files": {name: {"path": str(path.relative_to(PROJECT_ROOT)),
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for name, path in (("module", SOURCE), ("box", BOX_SOURCE))},
        "construction_files": {str(path.relative_to(PROJECT_ROOT)):
                               hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (PROJECT_ROOT / "src/vault/shell.py", PROJECT_ROOT / "src/vault/box.py")},
        "module_registration": {
            "original_axis_origin_mm": SOURCE_ORIGIN[[0, 2, 1]].tolist(),
            "rotation_matrix": MODULE_ROTATION.tolist(),
            "determinant": float(np.linalg.det(MODULE_ROTATION)),
            "formula": "model = rotation_matrix @ (original - original_axis_origin_mm)",
            "historical_comparison_axis_map": HISTORICAL_MODULE_MAP.tolist(),
            "historical_comparison_determinant": float(np.linalg.det(HISTORICAL_MODULE_MAP)),
            "explanation": "The historical (X,Z,Y) map reflects handed features. "
                           "A proper rotation preserving travel and height is (-X,Z,Y), "
                           "placing the lower female pocket at -X and the upper at +X."},
        "box_registration": {"subtract_origin_mm": BOX_ORIGIN.tolist(),
                             "rotation_matrix": np.eye(3, dtype=int).tolist(), "determinant": 1.},
        "section_y_mm": SECTION_Y,
        "native_module_support_thickness_mm": 0,
        "probes": probes, "passed": all(probe["passed"] for probe in probes),
        "figure": str(image_path.relative_to(PROJECT_ROOT)),
        "limitations": "Local interface and handedness checks only; no simulated rail motion "
                       "or physical printer-fit qualification. Native box attachment recesses "
                       "retain their documented simplified contours."}
    report_path = PROJECT_ROOT / "research/runner_interfaces.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "probes": len(probes),
                      "report": str(report_path), "figure": str(image_path)}, indent=2))
    if not report["passed"]:
        raise SystemExit("Runner interface audit failed")


if __name__ == "__main__":
    main()
