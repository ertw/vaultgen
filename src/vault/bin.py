"""Native editable drawer containers in bed coordinates.

Gridfinity feet follow Gridfinity Rebuilt's primary standard.scad definitions.
Drawer-fit containers instead divide the native plain cavity into logical cells
and use a thin chamfered floor. Edge-connected cells share one floor and cavity;
disconnected selections are individually printable solids.
Miura walls are rigid paired planar facets, not a folding mechanism.
"""
from dataclasses import dataclass
from math import ceil, floor, sqrt

from .bin_config import BinConfiguration, PITCH


FOOT_HEIGHT = 4.75
FLOOR_TOP = 7.0
EDGE_GAP = .25
CORNER_RADIUS = 3.75
MIURA_PITCH = 14.0
MIURA_DEPTH = 1.3
JOINT_BLEND = 7.0
RIM_BLEND = 3.5


def _block(x0, y0, z0, x1, y1, z1):
    from build123d import Plane, Solid
    return Solid.make_box(x1-x0, y1-y0, z1-z0, Plane(origin=(x0,y0,z0)))


def _union(shapes):
    return shapes[0].fuse(*shapes[1:]).clean() if len(shapes) > 1 else shapes[0]


def _intersection(left, right):
    result = left.intersect(right)
    return _union(list(result)) if isinstance(result, list) else result


def bin_foot():
    """One unscaled nominal 41.5 mm rounded Gridfinity foot, centered in XY."""
    from build123d import Solid
    from .gridfinity import _section_wire
    return Solid.make_loft([_section_wire(size, radius, z) for z, size, radius in (
        (0., 35.6, .8), (.8, 37.2, 1.6), (2.6, 37.2, 1.6), (4.75, 41.5, 3.75))], ruled=True)


def _footprint(cells, inset, z, height, *, pitch_x=PITCH, pitch_y=PITCH,
               corner_radius=CORNER_RADIUS):
    """Rounded cells plus native bridges form arbitrary orthogonal outlines.

    The bridges erase internal boundaries while retaining rounded convex
    corners and continuous inset walls around holes and concave outlines.
    """
    from build123d import Solid
    from .shell import _rounded_rect
    cells = set(cells)
    solids = []
    radius = max(.05, corner_radius-inset+EDGE_GAP)
    for x, y in sorted(cells):
        x0, y0 = x*pitch_x+inset, y*pitch_y+inset
        x1, y1 = (x+1)*pitch_x-inset, (y+1)*pitch_y-inset
        solids.append(Solid.extrude(_rounded_rect(x0,y0,x1,y1,radius,
            lambda x,y: (x,y,z)), (0,0,height)))
        if (x+1,y) in cells:
            solids.append(_block((x+.5)*pitch_x,y0,z,(x+1.5)*pitch_x,y1,z+height))
        if (x,y+1) in cells:
            solids.append(_block(x0,(y+.5)*pitch_y,z,x1,(y+1.5)*pitch_y,z+height))
        if {(x+1,y),(x,y+1),(x+1,y+1)} <= cells:
            # Pairwise bridges leave an inset-sized square at a four-cell
            # junction. Fill the shared interior for BOTH floor and cavity,
            # otherwise full drawers acquire a hole and a phantom post.
            solids.append(_block((x+.5)*pitch_x,(y+.5)*pitch_y,z,
                                 (x+1.5)*pitch_x,(y+1.5)*pitch_y,z+height))
    return _union(solids)


def boundary_segments(cells, *, pitch_x=PITCH, pitch_y=PITCH):
    """Merge collinear exposed edges; each carries its inward-facing sign."""
    selected, runs = set(cells), {}
    for x,y in cells:
        for neighbor, axis, datum, start, inward in (
                ((x-1,y),'x',x,y,1), ((x+1,y),'x',x+1,y,-1),
                ((x,y-1),'y',y,x,1), ((x,y+1),'y',y+1,x,-1)):
            if neighbor not in selected:
                runs.setdefault((axis,datum,inward), []).append(start)
    result = []
    for (axis,datum,inward), indices in sorted(runs.items()):
        indices.sort()
        start = previous = indices[0]
        for index in indices[1:]+[None]:
            if index != previous+1:
                across, along = (pitch_x, pitch_y) if axis == 'x' else (pitch_y, pitch_x)
                result.append((axis, datum*across, start*along, (previous+1)*along, inward))
                start = index
            previous = index
    return result


@dataclass(frozen=True)
class _Panel:
    axis: str
    datum: float
    start: float
    end: float
    inward: int
    z0: float
    z1: float

    def point(self, u, z, depth):
        across = self.datum+self.inward*depth
        return (across,u,z) if self.axis == 'x' else (u,across,z)

    def block(self, depth0, depth1):
        a,b = self.point(self.start,self.z0,depth0), self.point(self.end,self.z1,depth1)
        return _block(*(min(x,y) for x,y in zip(a,b)), *(max(x,y) for x,y in zip(a,b)))


def miura_axial_thickness(thickness):
    """Plane separation that preserves target thickness normal to each facet."""
    slope = MIURA_DEPTH/(MIURA_PITCH/2)
    return thickness*sqrt(1+1.25*slope*slope)


def divider_segments(dividers, *, pitch_x=PITCH, pitch_y=PITCH):
    """Merge adjacent painted edges before constructing any wall geometry."""
    runs = {}
    for divider in dividers:
        datum = divider.x if divider.axis == 'x' else divider.y
        start = divider.y if divider.axis == 'x' else divider.x
        runs.setdefault((divider.axis, datum), []).append(start)
    result = []
    for (axis, datum), indices in sorted(runs.items()):
        indices.sort()
        start = previous = indices[0]
        for index in indices[1:] + [None]:
            if index != previous + 1:
                across, along = (pitch_x, pitch_y) if axis == 'x' else (pitch_y, pitch_x)
                result.append((axis, datum*across, start*along, (previous+1)*along))
                start = index
            previous = index
    return result


def _junctions(run, other_runs):
    """Coordinates where bounded perpendicular runs actually meet this run."""
    axis, datum, start, end = run[:4]
    return sorted({other[1] for other in other_runs
                   if other[0] != axis and start <= other[1] <= end
                   and other[2] <= datum <= other[3]})


def _clip_polygon(polygon, axis, value, keep):
    """Clip a native facet's local coordinates at a blend sampling station."""
    result = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        da, db = (a[axis]-value)*keep, (b[axis]-value)*keep
        if da >= -1e-8:
            result.append(a)
        if (da > 1e-8 and db < -1e-8) or (da < -1e-8 and db > 1e-8):
            ratio = da/(da-db)
            result.append(tuple(a[k]+ratio*(b[k]-a[k]) for k in range(3)))
    return result


def _smoothstep(value):
    value = max(0., min(1., value))
    return value*value*(3-2*value)


class _BlendThicknessError(ValueError):
    """A transition needs finer native facet sampling before it is built."""


class _BlendGeometryError(ValueError):
    """A transition sampling creates an inverted or invalid native facet."""


def _miura_sheet(panel, thickness, junctions=(), centered=False, floor_top=FLOOR_TOP,
                 blend_subdivisions=2, fold_step=MIURA_PITCH/2,
                 fold_rise=MIURA_PITCH/2, joint_blend=JOINT_BLEND,
                 rim_blend=RIM_BLEND, constrain_ends=False):
    """Sew a thin Miura wall with gradual, constant-web junction transitions.

    Each ordinary Miura facet retains the exact selected normal thickness.
    At the blend's multi-facet vertices, a constrained normal-offset fit joins
    the adjacent faces continuously. Blend face-center separation is bounded
    to 0.02 mm; there is no solid envelope or rectangular junction pad.
    """
    from collections import defaultdict
    import numpy as np
    from build123d import Face, Shell, Solid, Wire

    u0, u1, z0, z1 = panel.start, panel.end, panel.z0, panel.z1
    stops = sorted({u0, u1, *[u for u in junctions if u0 <= u <= u1]})
    u_stations = sorted({u0, u1, *[u+joint_blend*k/blend_subdivisions for u in stops
        for k in range(-blend_subdivisions,blend_subdivisions+1)
        if u0 < u+joint_blend*k/blend_subdivisions < u1]})
    z_stations = sorted({z0, z1, *[z for k in range(blend_subdivisions+1)
        for z in (floor_top+rim_blend*k/blend_subdivisions,
                  z1-rim_blend*k/blend_subdivisions) if z0 < z < z1]})
    polygons = []
    for j in range(floor((z0-floor_top)/fold_rise)-1, ceil((z1-floor_top)/fold_rise)+1):
        for i in range(floor(u0/fold_step)-2, ceil(u1/fold_step)+1):
            corners = [(ii*fold_step+(jj%2)*fold_step/2, floor_top+jj*fold_rise,
                        MIURA_DEPTH if ii%2 else 0.)
                       for ii, jj in ((i,j),(i+1,j),(i+1,j+1),(i,j+1))]
            for axis, value, keep in ((0,u0,1),(0,u1,-1),(1,z0,1),(1,z1,-1)):
                corners = _clip_polygon(corners, axis, value, keep)
            if len(corners) < 3:
                continue
            pieces = [corners]
            for axis, stations in ((0,u_stations[1:-1]),(1,z_stations[1:-1])):
                for value in stations:
                    split = []
                    for polygon in pieces:
                        if min(p[axis] for p in polygon)+1e-8 < value < max(p[axis] for p in polygon)-1e-8:
                            split.extend((_clip_polygon(polygon,axis,value,1),
                                          _clip_polygon(polygon,axis,value,-1)))
                        else:
                            split.append(polygon)
                    pieces = split
            for polygon in pieces:
                points = []
                for u, z, depth in polygon:
                    distance = min(u-u0, u1-u, *(abs(u-stop) for stop in stops))
                    amplitude = (_smoothstep(distance/joint_blend)
                                 * _smoothstep(min(z-floor_top,z1-z)/rim_blend))
                    depth = (depth-(MIURA_DEPTH/2 if centered else 0.))*amplitude
                    points.append((u,z,depth))
                for a, b in zip(points[1:-1], points[2:]):
                    # Clipping can leave a redundant point on a facet edge.
                    area2 = ((a[0]-points[0][0])*(b[1]-points[0][1])
                             -(a[1]-points[0][1])*(b[0]-points[0][0]))
                    if abs(area2) > 1e-8:
                        polygons.append([points[0],a,b])

    def key(point):
        return tuple(round(value,8) for value in point)

    def local(point):
        u,z,depth = point
        return np.array((depth,u,z))

    normals, face_normals = defaultdict(list), []
    for points in polygons:
        a,b,c = [local(point) for point in points]
        normal = np.cross(b-a,c-a)
        normal /= np.linalg.norm(normal)
        face_normals.append(normal)
        for point in points:
            normals[key(point)].append(normal)
    offsets = {}
    for point, adjacent in normals.items():
        adjacent = np.array(adjacent)
        # The small minimum-displacement term stabilizes nearly coplanar
        # vertices without changing the exact regular-facet axial offset.
        target = thickness/np.mean(adjacent[:,0])
        if constrain_ends:
            if min(abs(point[0]-u0),abs(point[0]-u1)) < 1e-7:
                # The zero-amplitude end joins a plain wall with exactly
                # the selected thickness. A micron-scale offset mismatch
                # would leave sliver faces below STL coordinate precision.
                offsets[point] = np.array([thickness,0.,0.])
                continue
            # Keep the drawer's cap and end boundaries exactly in their
            # native planes; tangential miter offsets remain free inside.
            free = [0]
            if min(abs(point[0]-u0),abs(point[0]-u1)) >= 1e-7:
                free.append(1)
            if min(abs(point[1]-z0),abs(point[1]-z1)) >= 1e-7:
                free.append(2)
            lhs = np.vstack((adjacent[:,free],.01*np.identity(len(free))))
            rhs = np.append(np.full(len(adjacent),thickness),[target*.01]+[0]*(len(free)-1))
            offset = np.zeros(3)
            offset[free] = np.linalg.lstsq(lhs,rhs,rcond=None)[0]
            offsets[point] = offset
        else:
            lhs = np.vstack((adjacent,.01*np.identity(3)))
            rhs = np.append(np.full(len(adjacent),thickness),[target*.01,0,0])
            offsets[point] = np.linalg.lstsq(lhs,rhs,rcond=None)[0]
    for points, normal in zip(polygons,face_normals):
        separation = np.mean([normal@offsets[key(point)] for point in points])
        if abs(separation-thickness) > .02:
            raise _BlendThicknessError('Miura blend exceeds normal wall-thickness tolerance')
        if constrain_ends:
            a,b,c = [local(point)+offsets[key(point)] for point in points]
            area2 = (b[1]-a[1])*(c[2]-a[2])-(b[2]-a[2])*(c[1]-a[1])
            if area2 <= 1e-10:
                raise _BlendGeometryError('Miura blend offsets invert a facet')

    def shifted(point):
        depth,u,z = local(point)+offsets[key(point)]
        return panel.point(u,z,depth)

    def face(points):
        return Face(Wire.make_polygon(points,close=True))

    faces, edges = [], {}
    for points in polygons:
        faces.extend((face([panel.point(*point) for point in points]),
                      face(list(reversed([shifted(point) for point in points])))))
        for a,b in zip(points,points[1:]+points[:1]):
            edge = tuple(sorted((key(a),key(b))))
            if edge in edges:
                del edges[edge]
            else:
                edges[edge] = (a,b)
    for a,b in edges.values():
        faces.extend((face([panel.point(*a),shifted(a),shifted(b)]),
                      face([panel.point(*a),shifted(b),panel.point(*b)])))
    solid = Solid(Shell(faces)).clean()
    if solid.volume < 0:
        solid.wrapped.Reverse()
    if not solid.is_valid:
        raise _BlendGeometryError('Invalid native bin Miura sheet')
    return solid


def build_bins(config=BinConfiguration(), progress=None):
    """Return one valid solid per connected region, all in a shared print frame."""
    if not isinstance(config, BinConfiguration):
        config = BinConfiguration.parse(config)
    thickness = config.wall_thickness_mm
    drawer = config.container_type == 'drawer'
    floor_top = config.floor_top_mm
    pitch = {'pitch_x': config.pitch_x_mm, 'pitch_y': config.pitch_y_mm}
    # The plain drawer has R3.5 cavity corners. A 0.25 mm inset follows
    # these with R3.25 corners; Gridfinity keeps its original foot outline.
    corner_radius = config.corner_radius_mm
    footprint = {**pitch, 'corner_radius': corner_radius}
    foot, result = None if drawer else bin_foot(), {}

    def miura_sheet(panel, junctions, *, centered=False):
        # Arbitrary drawer cell pitches meet the fold grid at arbitrary
        # phases. Refine only those blend facets that need it to retain the
        # selected normal thickness; the existing Gridfinity stays exact.
        fold = {}
        pattern_floor = floor_top
        if drawer:
            # Start a complete fold row inside the 0.05 mm floor overlap.
            # A separate flat sliver below a different pattern datum can
            # invert when its paired facets receive normal offsets.
            pattern_floor = panel.z0
            along = config.pitch_y_mm if panel.axis == 'x' else config.pitch_x_mm
            step = along/(2*max(1,round(along/MIURA_PITCH)))
            height = panel.z1-pattern_floor
            rise = height/max(1,round(height/(MIURA_PITCH/2)))
            fold = {'fold_step':step, 'fold_rise':rise,
                    'joint_blend':step, 'rim_blend':rise,
                    'constrain_ends':True}
        subdivisions = (2,4,6,8,12) if drawer else (2,)
        for count in subdivisions:
            try:
                return _miura_sheet(panel,thickness,junctions,centered,
                    floor_top=pattern_floor,blend_subdivisions=count,**fold)
            except (_BlendThicknessError,_BlendGeometryError):
                if count == subdivisions[-1]:
                    raise

    for index,cells in enumerate(config.components, 1):
        if progress:
            kind = 'drawer' if drawer else 'Gridfinity'
            progress(f'Constructing {kind} container {index} of {len(config.components)}')
        selected = set(cells)
        floor_bottom = config.foot_height_mm
        base = _footprint(cells, EDGE_GAP, floor_bottom, floor_top-floor_bottom,
                          **footprint)
        if drawer:
            # Clear the drawer's R1 floor fillet without losing space higher
            # in the box. This leaves a continuous 1.2 mm floor centrally.
            bottom_edges = [edge for edge in base.edges()
                if abs(edge.bounding_box().min.Z) < 1e-6
                and abs(edge.bounding_box().max.Z) < 1e-6]
            base = base.chamfer(.75, None, bottom_edges).clean()
        wall_bottom = floor_top-.05 if drawer else floor_top
        outside = _footprint(cells, EDGE_GAP, wall_bottom, config.height_mm-wall_bottom,
                             **footprint)
        inside = _footprint(cells, EDGE_GAP+thickness, floor_top-.01,
                            config.height_mm-floor_top+.02, **footprint)
        walls = outside.cut(inside).clean()
        dividers = [divider for divider in config.dividers if divider.adjacent_cells()[0] in selected]
        runs = divider_segments(dividers, **pitch)
        boundaries = boundary_segments(cells, **pitch)
        sheets = []
        for run in runs:
            axis, datum, start, end = run
            # A selected cell borders each side of every divider. Ending
            # inside that common rectangle preserves the outline gap and
            # still overlaps the thinnest T web by 0.075 mm.
            low,high = (start+EDGE_GAP,end-EDGE_GAP) if drawer else (start,end)
            panel = _Panel(axis,datum-thickness/2,low,high,1,
                           floor_top-.05,config.height_mm)
            if config.wall_pattern == 'miura':
                separator = miura_sheet(panel,
                    _junctions(run,[*runs,*boundaries]),centered=True)
            else:
                separator = panel.block(0,thickness)
            sheets.append(separator)
        if config.wall_pattern == 'miura':
            cutouts = []
            for boundary in boundaries:
                axis, datum, start, end, inward = boundary
                # Only the curved corner attachment stays plain. Grid marks
                # and dividers that stop elsewhere never interrupt this run.
                low, high = start+corner_radius+EDGE_GAP, end-corner_radius-EDGE_GAP
                if drawer:
                    along = config.pitch_y_mm if axis == 'x' else config.pitch_x_mm
                    half_step = along/(4*max(1,round(along/MIURA_PITCH)))
                    # A corner tangent a few hundredths from a fold station
                    # would leave skinny clipped triangles that invert when
                    # offset. Retain the thin corner wall up to the next
                    # complete half-fold instead.
                    low = ceil((low-1e-8)/half_step)*half_step
                    high = floor((high+1e-8)/half_step)*half_step
                panel = _Panel(axis,datum+inward*EDGE_GAP,low,high,inward,
                               floor_top-.05,config.height_mm)
                cutouts.append(panel.block(-.01,MIURA_DEPTH+thickness+1))
                junctions = _junctions(boundary,runs)
                sheets.append(miura_sheet(panel,junctions))
            walls = walls.cut(*cutouts).clean()
        if sheets:
            if drawer:
                walls = walls.fuse(*sheets).clean()
            else:
                walls = _intersection(walls.fuse(*sheets).clean(),outside).clean()
        feet = [] if drawer else [foot.translate(((x+.5)*PITCH,(y+.5)*PITCH,0)) for x,y in cells]
        part = base.fuse(walls,*feet).clean()
        if not part.is_valid or len(part.solids()) != 1 or len(part.shells()) != 1:
            raise ValueError('Expected each container to be one valid solid and shell '
                             f'(valid={part.is_valid}, solids={len(part.solids())}, '
                             f'shells={len(part.shells())})')
        name = f'bin_{index:02d}'
        part.label = f'{config.name} · Container {index}'
        result[name] = part
    return result
