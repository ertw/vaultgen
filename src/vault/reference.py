"""Reference-mesh coordinates and the explicitly excluded cosmetic regions.

Only measurement/validation code reads the purchased STL. Model construction does
not depend on this file or on trimesh.
"""
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT_ROOT / 'original_files/01. DRAWERS/01. S Families/S4/Modules/S4 Module 1f.stl'
# Preserve the original source's sub-millimetre offsets. Modelling coordinates:
# X = width, Y = drawer travel (closed back at 0), Z = sleeve height.
SOURCE_ORIGIN = np.array([9001.650390625, 583.0028686523438, 727.5916137695312])
DECORATION_BOXES = {
    'back_brand_and_three_ovals': [[-66, -0.02, 8], [66, 0.62, 39]],
    'align_text_and_arrow': [[-27.3, 18.1, -0.02], [27.3, 31.5, 0.62]],
    'raised_S4': [[-24, 55.5, -0.32], [23, 88, 0.02]],
    'alignment_groove_shell': [[-75.6, 31.83, -.02], [75.6, 33.17, .67]],
    'alignment_groove_dovetail_left': [[-56.7, 31.83, -4.99], [-39.9, 33.17, -4.30]],
    'alignment_groove_dovetail_right': [[39.9, 31.83, -4.99], [56.7, 33.17, -4.30]],
}


# Expected planes for the intentionally restored skins. Groove endpoints enter
# curved shell corners; only the originally planar portions get plane probes.
CLEANUP_PATCHES = {
    'back_brand_and_three_ovals': (1, 0., (-66., 66.), (8., 39.)),
    'align_text_and_arrow': (2, 0., (-27.3, 27.3), (18.1, 31.5)),
    'raised_S4': (2, 0., (-24., 23.), (55.5, 88.)),
    'alignment_groove_center': (2, 0., (-43.9, 43.9), (31.83, 33.17)),
    'alignment_groove_left_skin': (2, 0., (-67., -57.8), (31.83, 33.17)),
    'alignment_groove_right_skin': (2, 0., (57.8, 67.), (31.83, 33.17)),
    'alignment_groove_left_crown': (2, -4.96942, (-54.5, -42.), (31.83, 33.17)),
    'alignment_groove_right_crown': (2, -4.96942, (42., 54.5), (31.83, 33.17)),
}


def load_reference(path: Path = SOURCE):
    import trimesh
    mesh = trimesh.load_mesh(path)
    mesh.vertices = mesh.vertices[:, [0, 2, 1]] - SOURCE_ORIGIN
    mesh.faces = mesh.faces[:, ::-1]
    return mesh


def decoration_mask(points):
    """Small explicit bounds, never entire faces/connector regions."""
    points = np.asarray(points)
    mask = np.zeros(len(points), dtype=bool)
    for low, high in DECORATION_BOXES.values():
        mask |= ((points >= low) & (points <= high)).all(axis=1)
    return mask


def mating_region_masks(points):
    """Conservative S4 1F regions checked separately from its outside styling.

    These masks select points for additional stricter checks; they do not
    exclude anything from the full retained-surface comparison. Bounds include
    the complete connector skins and the functional sleeve cuts, not just the
    nominally flat contact strips. Some adjacent flat skin is included too.
    """
    points = np.asarray(points)
    x, y, z = points.T
    ax = np.abs(x)
    return {
        'stacking_connectors': (z < -.01) | (z > 47.01),
        'stacking_tracks': (np.abs(ax - 45.4814) <= 3.76) & (y >= 102.16)
                            & (y <= 163.44) & (z >= 46.0) & (z <= 47.01),
        'drawer_cavity': (ax < 67.65) & (y >= 1.99) & (z >= 2.9) & (z <= 44.1),
        'side_runners': (ax >= 67.63) & (ax <= 79.40) & (y >= 1.99)
                        & (z >= 9.49) & (z <= 37.52),
        'runner_mouth_recesses': (ax >= 67.63) & (ax <= 79.40) & (y >= 182.28)
                                 & (z >= 6.48) & (z <= 40.52),
        'mounting_bores': (np.abs(ax - 74.2461) <= 2.81) & (y <= 100.01)
                          & ((np.abs(z - 4.7535) <= 2.81) | (np.abs(z - 42.2529) <= 2.81)),
        'side_stopper_slots': (ax >= 79.38) & (np.abs(y - 122.55005) <= 9.32)
                              & (np.abs(z - 23.5009) <= 4.14),
        'drawer_retention_catches': (ax <= 10.5) & (y >= 178.89) & (y <= 183.61)
                                    & ((z <= 3.1) | (z >= 43.9)),
        'rear_entry_reliefs': (ax >= 13.35) & (ax <= 16.91) & (y <= 5.98) & (z >= 44.3),
    }
