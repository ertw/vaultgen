"""Reusable lower outer hook in the left module's local mating frame.

X=0 is the left outside wall and positive X points inward. Y=0 is the open
mouth and negative Y points toward the back. Z=0 is the lower skin. Place the
nominal S4 hook with translate((-82.4004, 188.1, 0)); mirror X for the right.
"""
from dataclasses import dataclass, fields
from math import sqrt, atan2, cos, sin, isfinite
from build123d import Edge, Wire, Face, Solid, Plane


@dataclass(frozen=True)
class LowerHookDimensions:
    # Reach through the rounded sleeve corner, rather than leave a thin cap
    # exposed underneath it. This prism is hidden after the assembly union.
    root_overlap: float = .25
    crown_depth: float = 4.4477
    outer_crown_inset: float = 7.46
    outer_root_inset: float = 11.2036
    inner_inset: float = 20.6602
    flank_slope: float = 1.1111
    inner_round: float = 1.0
    back_offset: float = 18.3
    back_radius: float = 5.0
    side_sweep: float = 4.7998

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field.name} must be finite and positive")
        if not self.outer_crown_inset < self.outer_root_inset < self.inner_inset:
            raise ValueError("Hook insets must run from outer crown to root to inner wall")
        shoulder_depth = (self.outer_root_inset-self.outer_crown_inset)/self.flank_slope
        if self.crown_depth <= shoulder_depth + .76*self.inner_round:
            raise ValueError("Hook crown must leave room below the flank for its corner blend")


def _plan_wire(z, left, left_top, right_top, side_height, dimensions):
    """Rounded back and the fixed S-shaped outer boundary before flank trim."""
    right = dimensions.inner_inset
    back = -dimensions.back_offset
    outer = dimensions.outer_crown_inset
    side_y = back - side_height
    front_x = outer + dimensions.side_sweep
    front_y = back - 39.8
    point = lambda x, y: (x, y, z)
    factor = .55228475
    front = [point(front_x, back - 33.5167), point(front_x, back - 25.0023),
             point(outer, back - 22.4095), point(outer, back - 14.6215)]
    edges = [
        Edge.make_line(point(front_x, front_y), point(right, front_y)),
        Edge.make_line(point(right, front_y), point(right, side_y)),
        Edge.make_bezier(point(right, side_y), point(right, side_y + factor * side_height),
                         point(right_top + factor * (right - right_top), back), point(right_top, back)),
        Edge.make_line(point(right_top, back), point(left_top, back)),
        Edge.make_bezier(point(left_top, back), point(left_top - factor * (left_top - left), back),
                         point(left, side_y + factor * side_height), point(left, side_y)),
        Edge.make_line(point(left, side_y), front[-1]),
        Edge.make_bezier(*reversed(front)),
        Edge.make_line(front[0], point(front_x, front_y)),
    ]
    return Wire(edges)


def _entry_ramp(dimensions):
    """Circular lead-in with a compact loft through the inner corner blend."""
    d = dimensions
    root = (-d.back_offset - 37.52255, -10.00275)
    root_radius = 10.0535
    # Fraction across the inner round, center setback, crown radius.
    sections = [(0,25.9754,6.9911),(.24,26.0646,6.8425),(.5,26.2122,6.9180),
                (.75,26.2056,8.0908),(.9,26.1092,9.9562),(1,26.2493,13.1262)]
    def profile(x, fraction, setback, radius):
        bottom = -d.crown_depth + d.inner_round * (1-sqrt(1-fraction*fraction))
        crown = (-d.back_offset-setback, bottom+radius)
        dx,dz = crown[0]-root[0],crown[1]-root[1]
        length = sqrt(dx*dx+dz*dz)
        along = (root_radius**2-radius**2+length**2)/(2*length)
        cross = sqrt(max(0,root_radius**2-along**2))
        join = (root[0]+along*dx/length+cross*dz/length,
                root[1]+along*dz/length-cross*dx/length)
        high = (root[0]+sqrt(root_radius**2-root[1]**2),0)
        low = (crown[0],bottom)
        def midpoint(center,a,b):
            aa=atan2(a[1]-center[1],a[0]-center[0]);bb=atan2(b[1]-center[1],b[0]-center[0])
            r=sqrt((a[0]-center[0])**2+(a[1]-center[1])**2)
            return (center[0]+r*cos((aa+bb)/2),center[1]+r*sin((aa+bb)/2))
        p=lambda yz:(x,*yz)
        top=d.root_overlap; rear=-d.back_offset+1.2
        return Wire([
            Edge.make_three_point_arc(p(low),p(midpoint(crown,low,join)),p(join)),
            Edge.make_three_point_arc(p(join),p(midpoint(root,join,high)),p(high)),
            Edge.make_line(p(high),p((high[0],top))),
            Edge.make_line(p((high[0],top)),p((rear,top))),
            Edge.make_line(p((rear,top)),p((rear,bottom))),
            Edge.make_line(p((rear,bottom)),p(low)),
        ])
    inner_start=d.inner_inset-d.inner_round
    x0=d.outer_crown_inset-5
    main=Solid.extrude(Face(profile(x0,*sections[0])),(inner_start-x0,0,0))
    wires=[profile(inner_start+d.inner_round*u,u,y,r) for u,y,r in sections]
    return main.fuse(Solid.make_loft(wires,ruled=True)).clean()

def lower_outer_hook(dimensions: LowerHookDimensions = LowerHookDimensions()):
    """Build the flank, shoulder and rounded crown from six compact outlines."""
    outer_root = dimensions.outer_root_inset
    outer = dimensions.outer_crown_inset
    inner = dimensions.inner_inset
    transition = -(outer_root - outer) / dimensions.flank_slope
    bottom = -dimensions.crown_depth
    radius = dimensions.back_radius
    midpoint = (outer_root + inner) / 2
    middle_z = transition / 2
    middle_left = (outer_root + outer) / 2
    root = _plan_wire(0, outer_root, midpoint - .01,
                      midpoint + .01, (inner - outer_root) / 2, dimensions)
    middle = _plan_wire(middle_z, middle_left, middle_left + .995 * radius,
                        inner - .973 * radius, .96 * radius, dimensions)
    shoulder = _plan_wire(transition, outer, outer + 1.005 * radius,
                          inner - radius, .955 * radius, dimensions)
    crown = _plan_wire(bottom, outer, outer + .8 * radius,
                       inner - radius, radius, dimensions)
    rounded_shoulder = _plan_wire(bottom + .76 * dimensions.inner_round, outer, outer + .854 * radius,
                                    inner - radius, .9633 * radius, dimensions)
    lower_shoulder = _plan_wire(bottom + .45 * dimensions.inner_round, outer, outer + .804 * radius,
                                 inner - radius, .998 * radius, dimensions)
    body = Solid.make_loft([root, middle, shoulder, rounded_shoulder, lower_shoulder, crown], ruled=True)
    body = body.fuse(Solid.extrude(Face(root), (0, 0, dimensions.root_overlap))).clean()

    # The fixed cubic side is trimmed by an analytic flank. A 1 micron overlap
    # avoids coincident loft/flank edges in the Boolean without a visible step.
    y_start = -dimensions.back_offset - 42
    y_length = 45
    point = lambda x, z: (x, y_start, z)
    overlap = .001
    wedge = Face(Wire.make_polygon([
        point(outer - 5, 1), point(outer_root + overlap, 1),
        point(outer_root + overlap, 0), point(outer + overlap, transition),
        point(outer - 5, transition),
    ], close=True))
    body = body.cut(Solid.extrude(wedge, (0, y_length, 0)))
    corner_radius = dimensions.inner_round
    corner_box = Solid.make_box(corner_radius, y_length, corner_radius,
                                Plane(origin=(inner - corner_radius, y_start, bottom)))
    corner_cylinder = Solid.make_cylinder(corner_radius, y_length,
        Plane(origin=(inner - corner_radius, y_start, bottom + corner_radius), z_dir=(0, 1, 0)))
    body = body.cut(corner_box.cut(corner_cylinder))
    return body.intersect(_entry_ramp(dimensions))[0]
