"""Native symmetric underside latch, flat on Z=0 for printing.

The long arms use editable cubic curves; no purchased mesh or sampled outline
is a construction input. Clearance retreats the outline rather than scaling
its attachment spacing. Printed fit and latch force require a physical trial.
"""
from dataclasses import dataclass
from math import isfinite

from build123d import Edge, Face, Kind, Plane, Solid, Wire
from .accessories import one


@dataclass(frozen=True)
class LatchDimensions:
    edge_clearance: float = .10
    thickness_clearance: float = .15

    def __post_init__(self):
        for value in (self.edge_clearance, self.thickness_clearance):
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= .25:
                raise ValueError('Latch allowances must be between 0 and 0.25 mm')


def latch_outline():
    edges = []
    current = (0, 19.648)

    def point(p):
        return (*p, 0)

    def line(end):
        nonlocal current
        edges.append(Edge.make_line(point(current), point(end)))
        current = end

    def arc(mid, end):
        nonlocal current
        edges.append(Edge.make_three_point_arc(point(current), point(mid), point(end)))
        current = end

    def curve(control1, control2, end):
        nonlocal current
        edges.append(Edge.make_bezier(*map(point, (current, control1, control2, end))))
        current = end

    # Central V seat and outside of the broad flexible arm.
    arc((1.148, 19.876), (2.121, 20.527))
    line((9.172, 27.573))
    curve((30.0, 18.4), (31.9, 20.8), (34.766, -18.25))
    arc((35.48, -18.76), (36.087, -18.086))
    # Long narrow slot and the inward-pointing upper hook.
    line((34.22, 7.0))
    curve((33.8, 12.0), (35.6, 18.0), (35.296, 23.6))
    arc((35.07, 24.75), (34.417, 25.721))
    line((28.263, 31.875))
    arc((27.613, 35.144), (30.385, 37.289))
    line((35.382, 37.289))
    arc((37.503, 36.41), (38.382, 34.289))
    line((38.382, 23.0))
    curve((38.382, 10.0), (39.4, -2.0), (40.376, -12.015))
    # Small detent relief and the outer insertion lead.
    line((39.8, -13.01))
    arc((39.82, -14.05), (40.7, -14.504))
    arc((41.08, -14.43), (41.4, -14.22))
    line((41.93, -13.68)); line((42.19, -13.575)); line((48.0, -13.269))
    arc((48.25, -13.39), (48.278, -13.6))
    line((42.44, -21.967))
    curve((40.4, -24.9), (34.8, -25.5), (32.37, -23.73))
    curve((30.7, -22.5), (29.9, -20.8), (29.787, -18.797))
    # Inside of the broad arm blends into the finger ring.
    curve((28.3, 3.0), (25.7, 14.1), (15.4, 19.332))
    curve((7.4, 23.6), (5.6, 10.9), (6.0, 7.1))
    curve((6.2, -2.0), (9.0, -11.5), (11.482, -19.276))
    curve((12.3, -22.1), (12.45, -23.2), (12.45, -24.839))
    arc((8.803, -33.642), (0, -37.289))
    mirrored = [edge.mirror(Plane.YZ).reversed() for edge in reversed(edges)]
    return Wire(edges + mirrored)


def build_latch(dimensions=None):
    d = dimensions or LatchDimensions()
    outline = latch_outline()
    if d.edge_clearance:
        outline = outline.offset_2d(-d.edge_clearance, kind=Kind.ARC)
    height = 4.5 - d.thickness_clearance
    body = Solid.extrude(Face(outline), (0, 0, height))
    # Both faces of the V seat have the measured 1.5 mm insertion chamfer.
    seat_edges = []
    for edge in body.edges():
        bounds = edge.bounding_box()
        on_face = abs(bounds.min.Z) < 1e-5 or abs(bounds.min.Z - height) < 1e-5
        if (bounds.size.Z < 1e-5 and on_face and bounds.min.Y > 19
                and max(abs(bounds.min.X), abs(bounds.max.X)) < 9.4):
            seat_edges.append(edge)
    body = body.chamfer(1.5, None, seat_edges)
    # Preserve the double countersink on the finger opening and its 0.5 mm land.
    center = (0, -24.839)
    bore = Solid.make_cylinder(6.081, height, Plane(origin=(*center, 0)))
    lower = Solid.make_cone(8.081, 6.081, 2, Plane(origin=(*center, 0)))
    upper = Solid.make_cone(6.081, 8.081, 2, Plane(origin=(*center, height - 2)))
    body = one(body.cut(bore, lower, upper))
    # STEP cannot reliably sew surfaces extruded from OCC offset curves.
    # Convert that native surface representation before export, retaining the
    # same strict solid/STEP/mesh checks (no mesh-based reconstruction).
    from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
    from .exports import precise_volume
    converted = one(Solid(BRepBuilderAPI_NurbsConvert(body.wrapped, True).Shape()))
    if abs(precise_volume(converted) - precise_volume(body)) / precise_volume(body) > 1e-5:
        raise ValueError('Latch surface conversion changed its volume')
    return converted
