"""One-off, one-less-loop spring for a full circular facade screw boss.

This experiment is deliberately separate from the standard accessory and
generator catalog. Coordinates and the flat Z=0 print bed match ``accessories``.
Removing a compliant loop changes restoring force; geometric clearance does
not establish printed fit, spring travel, or fatigue life.
"""
from math import sqrt

from build123d import Compound, Edge, Face, Plane, Solid, Wire

from .accessories import extrude, one


# Center of the unchanged circular seating arc through (10.6, +/-6.325)
# and (19.9, 0). The facade screw riser's complete circle is R6.8.
BOSS_CENTER_X = (19.9**2 - 10.6**2 - 6.325**2) / (2 * (19.9 - 10.6))
BOSS_CENTER_Y = 0.0
BOSS_RADIUS = 6.8

# Include the remaining compliant strip and the entire new lower connection
# up to its mounting-fork root. Exclude the intentionally close seating
# fork, whose fit is unchanged and must not be mistaken for flexure clearance.
FLEXURE_MAX_X = 9.283


def flexible_region(shape):
    """Return the moving-strip diagnostic region, including its lower bridge."""
    bounds = shape.bounding_box()
    cutter = Solid.make_box(
        FLEXURE_MAX_X - bounds.min.X + 1,
        bounds.size.Y + 2,
        bounds.size.Z + 2,
        Plane(origin=(bounds.min.X - 1, bounds.min.Y - 1, bounds.min.Z - 1)),
    )
    region = shape.intersect(cutter)
    pieces = region if isinstance(region, list) else [region]
    # The cut plane also touches the unchanged fork side. Keep volumetric
    # pieces only, so coincident fork faces do not enter the flexure metric.
    return Compound([solid for piece in pieces for solid in piece.solids()])


def build_spring_trial():
    """Build a native continuous spring with the fork-adjacent upper U omitted.

    The left contact finger, remaining tall loop, fork seating arc, external
    envelope and thickness ramp retain the standard nominal dimensions. A
    rounded lower bridge replaces the upper U and its two long legs. Its
    roughly 3.9 mm width matches the former flexible strip; broad outer turns
    avoid a square reentrant corner at the shortened spring's root.
    """
    edges = []
    current = (-22.292, -2.5)

    def line(end):
        nonlocal current
        edges.append(Edge.make_line((*current, 0), (*end, 0)))
        current = end

    def arc(mid, end):
        nonlocal current
        edges.append(Edge.make_three_point_arc((*current, 0), (*mid, 0), (*end, 0)))
        current = end

    # Unchanged contact end and first tall flexible loop.
    arc((-23.737, 0), (-22.292, 2.32))
    line((-22.292, 8.75))
    arc((-21.47, 9.55), (-20.65, 8.75))
    line((-18.417, -13))
    arc((-17.292, -14.125), (-16.167, -13))
    line((-16.167, 13))
    arc((-11.167, 18), (-6.167, 13))
    line((-6.167, -13))

    # Omit the upper U centered at (1.083, 13). Tangent R1.6 turns
    # instead carry the load along the bottom and into the original fork.
    diagonal = 1.6 / sqrt(2)
    arc((-4.567 - diagonal, -13 - diagonal), (-4.567, -14.6))
    line((7.683, -14.6))
    arc((7.683 + diagonal, -13 - diagonal), (9.283, -13))
    line((9.283, -7.275))

    # Unchanged mounting fork and circular seating notch.
    arc((9.58, -6.57), (10.6, -6.325))
    arc((19.9, 0), (10.6, 6.325))
    arc((9.58, 6.57), (9.283, 7.275))
    line((9.283, 15.5))
    arc((10.162, 17.621), (12.283, 18.5))
    line((20.737, 18.5))
    arc((22.858, 17.621), (23.737, 15.5))
    line((23.737, -15.5))
    arc((22.858, -17.621), (20.737, -18.5))

    # The broad bottom bridge remains inside the original print envelope.
    # R5.5 blends it into the unchanged left descending arm tangentially.
    line((-4.542, -18.5))
    diagonal = 5.5 / sqrt(2)
    arc((-4.542 - diagonal, -13 - diagonal), (-10.042, -13))
    line((-10.042, 13))
    arc((-11.167, 14.125), (-12.292, 13))
    line((-12.292, -13))
    arc((-17.292, -18), (-22.292, -13))
    line((-22.292, -2.5))

    blank = extrude(Wire(edges), 5.155)
    # Preserve the thin contact finger and original rise into the fork.
    roof = Face(Wire.make_polygon([
        (-30, -25, 0), (30, -25, 0), (30, -25, 5.155),
        (12.5, -25, 5.155), (9.5, -25, 4.38), (-3, -25, 4.38),
        (-14.7, -25, 1.605), (-30, -25, 1.605),
    ], close=True))
    return one(blank.intersect(Solid.extrude(roof, (0, 50, 0))))
