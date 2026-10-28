"""Native symmetric underside latch, flat on Z=0 for printing.

The long arms use editable cubic curves; no purchased mesh or sampled outline
is a construction input. Clearance retreats the outline rather than scaling
its attachment spacing. Printed fit and latch force require a physical trial.
"""
from dataclasses import dataclass
from math import isfinite, sqrt

from build123d import Edge, Face, GeomType, Kind, Plane, Solid, Wire
from .accessories import one


@dataclass(frozen=True)
class LatchDimensions:
    edge_clearance: float = .10
    thickness_clearance: float = .15
    opening_chamfer: float = .30
    top_fillet_radius: float = .50

    def __post_init__(self):
        for value in (self.edge_clearance, self.thickness_clearance):
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= .25:
                raise ValueError('Latch allowances must be between 0 and 0.25 mm')
        if (type(self.opening_chamfer) not in (int, float)
                or not isfinite(self.opening_chamfer) or not 0 <= self.opening_chamfer <= .30):
            raise ValueError('Latch opening chamfer must be between 0 and 0.30 mm')
        if (type(self.top_fillet_radius) not in (int, float)
                or not isfinite(self.top_fillet_radius) or not 0 <= self.top_fillet_radius <= .50):
            raise ValueError('Latch top fillet radius must be between 0 and 0.50 mm')


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


def latch_opening():
    """Rounded finger aperture continuing along the central tongue.

    The 7.781 mm finger radius and 0.3 mm lower chamfer retain the previous
    8.081 mm lower-face radius, replacing its deep double countersink. The narrow
    end is R2.4, leaving the V seat and arm junctions solid. Curves meet
    tangentially so the opening has no sharp internal stress raisers.
    """
    radius, center_y = 7.781, -24.839
    half_width, tip_center_y = 2.4, 8.8
    current = (0, center_y - radius)
    edges = []

    def point(p):
        return (*p, 0)

    def arc(mid, end):
        nonlocal current
        edges.append(Edge.make_three_point_arc(point(current), point(mid), point(end)))
        current = end

    def curve(control1, control2, end):
        nonlocal current
        edges.append(Edge.make_bezier(*map(point, (current, control1, control2, end))))
        current = end

    arc((radius / sqrt(2), center_y - radius / sqrt(2)), (radius, center_y))
    curve((radius, -21.5), (8.4, -23.4), (6.6, -16))
    curve((4.8, -8.6), (half_width, .5), (half_width, tip_center_y))
    arc((half_width / sqrt(2), tip_center_y + half_width / sqrt(2)),
        (0, tip_center_y + half_width))
    mirrored = [edge.mirror(Plane.YZ).reversed() for edge in reversed(edges)]
    return Wire(edges + mirrored)


def _fillet_outline(outline):
    """Represent native offset curves as splines before rolling their edges.

    OCC cannot reliably fillet surfaces extruded directly from offset curves.
    Keep the shared vertices and edge orientation when converting those native
    curves; construction still uses no measured profiles or reference meshes.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.Geom import Geom_TrimmedCurve
    from OCP.GeomConvert import GeomConvert
    from OCP.TopExp import TopExp

    edges = []
    for edge in outline.edges():
        if edge.geom_type == GeomType.OFFSET:
            adaptor = edge.geom_adaptor()
            curve = GeomConvert.CurveToBSplineCurve_s(Geom_TrimmedCurve(
                adaptor.Curve().Curve(), adaptor.FirstParameter(), adaptor.LastParameter()))
            converted = Edge(BRepBuilderAPI_MakeEdge(
                curve, TopExp.FirstVertex_s(edge.wrapped), TopExp.LastVertex_s(edge.wrapped),
                curve.FirstParameter(), curve.LastParameter()).Edge())
            converted.wrapped.Orientation(edge.wrapped.Orientation())
            edges.append(converted)
        else:
            edges.append(edge)
    return Wire(edges)


def _round_top(body, height, radius):
    top_edges = [edge for face in body.faces()
                 if face.bounding_box().size.Z < 1e-5 and abs(face.center().Z - height) < 1e-5
                 for edge in face.edges()]
    if radius <= .15:
        return one(body.fillet(radius, top_edges))

    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet

    fillet = BRepFilletAPI_MakeFillet(body.wrapped)
    for edge in top_edges:
        fillet.Add(radius, edge.wrapped)
    for contour in range(1, fillet.NbContours() + 1):
        count = fillet.NbEdges(contour)
        edges = [Edge(fillet.Edge(contour, index)) for index in range(1, count + 1)]
        # The small detents and insertion tips cannot accept the main round.
        # Preserve their existing R0.15 blends, rolling all broad edges at the
        # requested radius in the same operation so their corners join cleanly.
        if all(abs(edge.center().X) > 39 and edge.center().Y < 0 for edge in edges):
            for index in range(1, count + 1):
                fillet.SetRadius(.15, contour, index)
        if any(edge.bounding_box().min.Y < -33 for edge in edges):
            # The continuous exterior around the finger ring starts and ends
            # at the two diagonal insertion leads. Taper those leads from the
            # small tip round to the full radius instead of creating a step.
            for edge in (edges[0], edges[-1]):
                bounds = edge.bounding_box()
                if max(abs(bounds.min.X), abs(bounds.max.X)) < 47:
                    raise ValueError('Latch insertion-lead fillet contour changed')
            fillet.SetRadius(.15, radius, contour, 1)
            fillet.SetRadius(radius, .15, contour, count)
    fillet.Build()
    if not fillet.IsDone():
        raise ValueError('Could not construct the latch top fillet')
    return one(Solid(fillet.Shape()))


def build_latch(dimensions=None):
    from .exports import precise_volume

    d = dimensions or LatchDimensions()
    outline = latch_outline()
    if d.edge_clearance:
        outline = outline.offset_2d(-d.edge_clearance, kind=Kind.ARC)
    height = 4.5 - d.thickness_clearance
    body = Solid.extrude(Face(outline), (0, 0, height))
    compatible = Solid.extrude(Face(_fillet_outline(outline)), (0, 0, height))
    if abs(precise_volume(compatible) - precise_volume(body)) / precise_volume(body) > 1e-5:
        raise ValueError('Latch outline conversion changed its volume')
    body = one(compatible)
    # Both faces of the V seat have the measured 1.5 mm insertion chamfer.
    seat_edges = []
    for edge in body.edges():
        bounds = edge.bounding_box()
        on_face = abs(bounds.min.Z) < 1e-5 or abs(bounds.min.Z - height) < 1e-5
        if (bounds.size.Z < 1e-5 and on_face and bounds.min.Y > 19
                and max(abs(bounds.min.X), abs(bounds.max.X)) < 9.4):
            seat_edges.append(edge)
    body = body.chamfer(1.5, None, seat_edges)
    body = one(body.cut(Solid.extrude(Face(latch_opening()), (0, 0, height))))
    if d.opening_chamfer:
        # Select the enclosed wires on the flat faces, never the exterior
        # mating profile, spring slots, or existing V-seat chamfers.
        opening_edges = [edge for face in body.faces()
                         if face.bounding_box().size.Z < 1e-5 and abs(face.center().Z) < 1e-5
                         for wire in face.inner_wires() for edge in wire.edges()]
        body = one(body.chamfer(d.opening_chamfer, None, opening_edges))
    # STEP cannot reliably sew surfaces extruded from OCC offset curves.
    # Convert that native surface representation before export, retaining the
    # same strict solid/STEP/mesh checks (no mesh-based reconstruction).
    from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
    converted = one(Solid(BRepBuilderAPI_NurbsConvert(body.wrapped, True).Shape()))
    if abs(precise_volume(converted) - precise_volume(body)) / precise_volume(body) > 1e-5:
        raise ValueError('Latch surface conversion changed its volume')
    if d.top_fillet_radius:
        converted = _round_top(converted, height, d.top_fillet_radius)
    return converted
