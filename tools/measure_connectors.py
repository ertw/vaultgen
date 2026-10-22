"""Measure editable connector outlines from the purchased STL.

Run ``python tools/measure_connectors.py`` in the project environment. This is
reverse-engineering tooling, never a model-build dependency. Each output feature
is a native ruled loft of measured XY sections. Source glyphs are excluded by
explicit mechanical feature regions. A contour tolerance of 0.006 mm retains
small radii and the original asymmetric fits without pretending they are circles.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import numpy as np
import trimesh
from shapely.geometry import Polygon, LineString, box
from shapely.ops import unary_union
from vault.reference import SOURCE, SOURCE_ORIGIN, load_reference

OUT = Path(__file__).resolve().parents[1] / 'research/legacy_profiles/connector_profiles.json'
CONTOUR_TOLERANCE = 0.006
INTERPOLATION_TOLERANCE = 0.012
MIN_STATION_STEP = 0.025
MESH = None
TOP_MESH = None
LOWER_MESH = None


def _closed_paths(segments):
    """Join triangle intersections without healing the reference mesh."""
    adjacency = {}
    for a, b in np.round(segments, 4):
        a, b = tuple(a), tuple(b)
        if a == b:
            continue
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    paths = []
    while adjacency:
        current = next((p for p, ns in adjacency.items() if len(ns) == 1), next(iter(adjacency)))
        points = [current]
        while current in adjacency:
            following = adjacency[current].pop()
            if not adjacency[current]:
                del adjacency[current]
            adjacency[following].remove(current)
            if not adjacency[following]:
                del adjacency[following]
            points.append(following)
            current = following
        # The float32 purchase mesh has a few tiny open seams. Closing
        # only gaps below 0.01 mm keeps those from discarding an entire rail.
        if len(points) > 3 and np.linalg.norm(np.asarray(points[0])-points[-1]) <= .01:
            polygon = Polygon(points).buffer(0)
            if isinstance(polygon, Polygon) and polygon.area > 0.001:
                paths.append(polygon)
    return paths


@lru_cache(maxsize=4096)
def _section(z):
    mesh=LOWER_MESH if z<0 else TOP_MESH if z>=47 else MESH
    segments = trimesh.intersections.mesh_plane(mesh, [0, 0, 1], [0, 0, z], cached_dots=mesh.vertices[:,2]-z)[:, :, :2]
    return _closed_paths(segments)


def _outline(z, region, recess=False):
    region_poly = box(*region)
    if recess:
        # The two long shallow detent tracks are enclosed holes in the top skin.
        candidates = [p for p in _section(z) if region_poly.contains(p.representative_point()) and p.area > 1]
    else:
        candidates = [p.intersection(region_poly) for p in _section(z) if region_poly.contains(p.representative_point())]
    candidates = [p for p in candidates if isinstance(p, Polygon) and p.area > .001]
    if not candidates:
        # Split closed-end dovetails clip through a larger source polygon.
        candidates = [p.intersection(region_poly) for p in _section(z)]
        candidates = [p for p in candidates if isinstance(p, Polygon) and p.area > .001]
    if not candidates:
        raise ValueError(f'No mechanical profile at Z={z} in {region}')
    polygon = max(candidates, key=lambda p: p.area).simplify(CONTOUR_TOLERANCE, preserve_topology=True)
    points = np.asarray(polygon.exterior.coords)[:-1]
    if not polygon.exterior.is_ccw:
        points = points[::-1]
    # A seam on the first upward left flank is stable even when float32 STL
    # noise makes different vertices the numerically leftmost one.
    y_seam = points[:, 1].min() + min(.05, (points[:, 1].max()-points[:, 1].min())/10)
    a, b = points, np.roll(points, -1, axis=0)
    hits = []
    for i, (start, end) in enumerate(zip(a, b)):
        if abs(end[1]-start[1]) > 1e-12:
            t = (y_seam-start[1])/(end[1]-start[1])
            if 0 <= t <= 1:
                hits.append((start[0]+t*(end[0]-start[0]), i, t))
    _, i, t = min(hits)
    seam = a[i]+t*(b[i]-a[i])
    points = np.vstack((seam, points[i+1:], points[:i+1]))
    keep = np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > .00002]
    points = points[keep]
    if np.linalg.norm(points[-1]-points[0]) < .00002:
        points = points[:-1]
    return points


def _parameterize(points):
    points = np.vstack((points, points[0]))
    u = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    return points, u/u[-1]


def _interpolated(a, b, t=.5):
    pa, ua = _parameterize(a)
    pb, ub = _parameterize(b)
    u = np.unique(np.r_[ua, ub])
    return np.column_stack([(1-t)*np.interp(u, ua, pa[:, k])+t*np.interp(u, ub, pb[:, k]) for k in range(2)])


def _feature(name, region, lower, upper, *, root=None, split_levels=(), recess=False):
    measured = {}
    def profile(z):
        z = round(float(z), 7)
        if z not in measured:
            measured[z] = _outline(z, region, recess)
        return measured[z]
    accepted = {}
    def subdivide(z0, z1, depth=0):
        p0, p1 = profile(z0), profile(z1)
        zm = (z0+z1)/2
        expected = Polygon(_interpolated(p0,p1)).buffer(0)
        actual = Polygon(profile(zm))
        deviation = expected.hausdorff_distance(actual)
        if deviation > INTERPOLATION_TOLERANCE and z1-z0 > MIN_STATION_STEP and depth < 12:
            subdivide(z0,zm,depth+1)
            subdivide(zm,z1,depth+1)
        else:
            accepted[z0], accepted[z1] = p0, p1
    levels = sorted(set([lower, upper, *[z for z in split_levels if lower<z<upper]]))
    for a,b in zip(levels,levels[1:]):
        subdivide(a,b)
    sections = [{'z':round(z,7), 'points':np.round(p,5).tolist()} for z,p in sorted(accepted.items())]
    if root is not None:
        index = -1 if root > upper else 0
        copy = {'z':root, 'points':sections[index]['points']}
        sections.append(copy)
        sections.sort(key=lambda section:section['z'])
    print(f'{name}: {len(sections)} sections, {sum(len(s["points"]) for s in sections)} points', flush=True)
    return {'name':name, 'operation':'cut' if recess else 'add', 'sections':sections}


def _align_landmarks(points, y):
    """Give corresponding contour branches fixed spline parameter intervals."""
    polygon = Polygon(points).simplify(.00001, preserve_topology=True)
    points = np.asarray(polygon.exterior.coords)[:-1]
    if not polygon.exterior.is_ccw:
        points = points[::-1]

    # Insert every crossing, including both sides of each U-shaped rail leg.
    expanded, marks = [], []
    for start, end in zip(points, np.roll(points, -1, axis=0)):
        expanded.append(start)
        if abs(start[1] - y) < 1e-7:
            marks.append(len(expanded) - 1)
        if abs(end[1] - start[1]) > 1e-12:
            fraction = (y - start[1]) / (end[1] - start[1])
            if 1e-7 < fraction < 1 - 1e-7:
                expanded.append(start + fraction * (end - start))
                marks.append(len(expanded) - 1)
    points = np.asarray(expanded)
    marks = sorted(set(marks))
    if len(marks) < 2:
        raise ValueError(f'No stable contour crossings at Y={y}')
    first = min(marks, key=lambda index: points[index, 0])
    points = np.roll(points, -first, axis=0)
    marks = sorted((index - first) % len(points) for index in marks)

    # Drop zero-length edges introduced by a preexisting seam, remapping marks.
    output, remapped = [], []
    for index, point in enumerate(points):
        if output and np.linalg.norm(output[-1] - point) < .00002:
            if index in marks:
                remapped.append(len(output) - 1)
            continue
        output.append(point)
        if index in marks:
            remapped.append(len(output) - 1)
    points = np.asarray(output)
    marks = sorted(set(remapped))
    count = len(marks)
    parameters = np.zeros(len(points) + 1)
    closed = np.vstack((points, points[0]))
    stops = marks + [len(points)]
    for interval, (start, end) in enumerate(zip(stops, stops[1:])):
        cumulative = np.r_[0, np.cumsum(np.linalg.norm(
            np.diff(closed[start:end + 1], axis=0), axis=1))]
        parameters[start:end + 1] = (interval + cumulative / cumulative[-1]) / count
    if not np.all(np.diff(parameters) > 0):
        raise ValueError(f'Non-monotone contour parameters at Y={y}')
    return np.round(points, 5).tolist(), np.round(parameters, 12).tolist(), count


def _anchor_seam(points, y):
    """Normalize source contours before registering their branch landmarks.

    Keep this intermediate rounding explicit so repeated measurement follows
    the same contour-normalization stages as the stored profile dataset.
    """
    polygon = Polygon(points).simplify(.00001, preserve_topology=True)
    points = np.asarray(polygon.exterior.coords)[:-1]
    if not polygon.exterior.is_ccw:
        points = points[::-1]
    hits = []
    for index, (start, end) in enumerate(zip(points, np.roll(points, -1, axis=0))):
        if abs(end[1] - start[1]) < 1e-12:
            continue
        fraction = (y - start[1]) / (end[1] - start[1])
        if 0 <= fraction <= 1:
            hits.append((start[0] + fraction * (end[0] - start[0]), index, fraction))
    _, index, fraction = min(hits)
    seam = points[index] + fraction * (points[(index + 1) % len(points)] - points[index])
    points = np.vstack((seam, points[index + 1:], points[:index + 1]))
    keep = np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > .00002]
    points = points[keep]
    if np.linalg.norm(points[0] - points[-1]) < .00002:
        points = points[:-1]
    return np.round(points, 5).tolist()


def _finish_features(features):
    """Remove the requested transverse notch and register corresponding contours.

    Register every crossing, not just the seam: the U-shaped upper rails have
    four contour branches, whose relative parameters must stay fixed while the
    slightly tilted crown plane clips the long closed-end legs.
    """
    for side, sign in [('left',-1),('right',1)]:
        name=f'lower_closed_end_dovetail_{side}'
        parts=[f for f in features if f['name'].startswith(name)]
        levels=sorted({section['z'] for f in parts for section in f['sections']
                       if -4.967<section['z']<=-.001}|{-4.967})
        xmin,xmax=(-58,-39) if sign<0 else (39,58)
        sections=[]
        for z in levels:
            a=Polygon(_outline(z,(xmin,-.01,xmax,32.505)))
            b=Polygon(_outline(z,(xmin,32.495,xmax,47)))
            outline=unary_union([a,b])
            if not isinstance(outline,Polygon):
                ya,yb=a.bounds[3]-.001,b.bounds[1]+.001
                left=a.intersection(LineString([(xmin,ya),(xmax,ya)]))
                right=b.intersection(LineString([(xmin,yb),(xmax,yb)]))
                bridge=Polygon([(left.bounds[0],ya),(left.bounds[2],ya),
                                (right.bounds[2],yb),(right.bounds[0],yb)])
                outline=unary_union([a,b,bridge])
            if not isinstance(outline,Polygon):
                raise ValueError(f'Failed to close alignment notch in {name} at {z}')
            points=np.asarray(outline.simplify(CONTOUR_TOLERANCE).exterior.coords)[:-1]
            sections.append({'z':z,'points':points.tolist()})
        # Float32 source points scatter around its nominal bottom plane.
        # Use the first complete outline at -4.967 for the -4.9685 crown cap.
        sections.insert(0,{'z':-4.9685,'points':sections[0]['points']})
        sections.append({'z':.02,'points':sections[-1]['points']})
        first=min(i for i,f in enumerate(features) if f in parts)
        features=[f for f in features if f not in parts]
        features.insert(first,{'name':name,'operation':'add','seam_y':20.,'sections':sections})
    for feature in features:
        sections=feature['sections']
        lower=max(min(p[1] for p in section['points']) for section in sections)
        upper=min(max(p[1] for p in section['points']) for section in sections)
        y=feature.get('seam_y',(lower+upper)/2)
        for section in sections:
            section['points'] = _anchor_seam(section['points'], y)
        y=round(y,5)
        if feature['name'].startswith('upper_outer_rail'):
            # Register at the measured inner-arc tangent. This keeps the
            # rounded tip aligned while the tilted crown clips the long leg.
            y=165.0999
        feature['seam_y']=round(y,5)
        crossing_counts=set()
        for section in sections:
            points,parameters,count=_align_landmarks(section['points'],y)
            section['points']=points
            section['parameters']=parameters
            crossing_counts.add(count)
        if len(crossing_counts)!=1:
            raise ValueError(f'Unstable contour correspondence: {feature["name"]}')
    return features


def main():
    global MESH, TOP_MESH, LOWER_MESH
    MESH = load_reference()
    heights=MESH.vertices[MESH.faces,2]
    TOP_MESH=trimesh.Trimesh(vertices=MESH.vertices,faces=MESH.faces[heights.max(axis=1)>=47],process=False)
    LOWER_MESH=trimesh.Trimesh(vertices=MESH.vertices,faces=MESH.faces[heights.min(axis=1)<=0],process=False)
    fingerprint=hashlib.sha256(SOURCE.read_bytes()+Path(__file__).read_bytes()).hexdigest()[:16]
    checkpoint=Path('/tmp/vault-connector-measurements')/fingerprint
    checkpoint.mkdir(parents=True,exist_ok=True)
    features=[]
    def add(name, region, lo, hi, **kw):
        saved=checkpoint/(name+'.json')
        if saved.exists():
            feature=json.loads(saved.read_text())
            print(f'{name}: cached {len(feature["sections"])} sections',flush=True)
        else:
            feature=_feature(name, region, lo, hi, **kw)
            saved.write_text(json.dumps(feature,separators=(',',':')))
        features.append(feature)
    for side, sign in [('left',-1),('right',1)]:
        def region(x0,y0,x1,y1):
            return (x0,y0,x1,y1) if sign>0 else (-x1,y0,-x0,y1)
        # Measure each side of the source's transverse notch separately.
        # _finish_features joins these outlines to remove the requested notch.
        add(f'lower_closed_end_dovetail_{side}_back',region(39,-.01,58,32.505),-4.969,-.001,root=.02,split_levels=[-4.5,-4.3,-4,-2,-.5])
        add(f'lower_closed_end_dovetail_{side}_tip',region(39,32.495,58,47),-4.969,-.001,root=.02,split_levels=[-4.5,-4.3,-4,-2,-.5])
        add(f'lower_alignment_tab_{side}',region(12,0,18,21),-5.1975,-.001,root=.02,split_levels=[-5,-4.5,-4,-2,-.5,-.1])
        add(f'lower_open_end_dovetail_{side}',region(30,140,60,177),-4.4976,-.001,root=.02,split_levels=[-4.4,-4,-3,-1,-.1])
        add(f'lower_open_end_detent_{side}',region(42,145,49,177),-5.2063,-4.47,split_levels=[-5.1,-4.9,-4.7,-4.5])
        add(f'lower_outer_hook_{side}',region(60,125,77,171),-4.4477,-.001,root=.02,split_levels=[-4.4,-4,-3,-2,-1,-.1])
        add(f'upper_outer_rail_{side}',region(57,0,83,177),47.001,51.6998,root=46.98,split_levels=[47.1,47.5,48,49,50,51,51.4,51.5,51.55,51.58,51.6,51.62,51.64,51.66,51.68,51.69,51.695])
        add(f'upper_alignment_tab_{side}',region(12,0,18,40),47.001,50.9993,root=46.98,split_levels=[47.1,47.5,48,49,50,50.5,50.8])
        add(f'upper_open_end_dovetail_{side}',region(8,135,38,177),47.001,51.8007,root=46.98,split_levels=[47.1,47.5,48,49,50,51,51.5,51.7,51.78])
    add('lower_open_end_dovetail_center',(-16,140,16,177),-4.4976,-.001,root=.02,split_levels=[-4.4,-4,-3,-1,-.1])
    add('upper_closed_end_locking_bridge',(-45,0,45,67),47.001,51.6991,root=46.98,split_levels=[47.1,47.4,47.7,48,49,50,51,51.4,51.6])
    features=_finish_features(features)
    segments=trimesh.intersections.mesh_plane(MESH,[1,0,0],[45.48,0,0])[:,:,[1,2]]
    points=np.unique(segments.reshape(-1,2),axis=0)
    points=points[(points[:,0]>102.17)&(points[:,0]<163.43)&(points[:,1]>46.3)&(points[:,1]<47.01)]
    points=points[np.argsort(points[:,0])]
    curve=np.asarray(LineString(points).simplify(.0015).coords)
    curve[:,1]=np.minimum(curve[:,1],47)
    curve[0]=[102.17297,47]
    curve[-1]=[163.42407,47]
    payload={'description':'Native connector ruled-loft section profiles, measured from the purchased STL. Decoration-free mechanical regions only; no source mesh is read by the model.',
        'source_file':SOURCE.name,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'source_axis_order':[0,2,1],'source_origin_after_permutation':SOURCE_ORIGIN.tolist(),
        'measurement':{'contour_tolerance_mm':CONTOUR_TOLERANCE,'interpolation_target_mm':INTERPOLATION_TOLERANCE,'minimum_station_step_mm':MIN_STATION_STEP,'coordinate_rounding_mm':.00001,'root_overlap_mm':.02,'section_parameter':'equal parameter intervals between all crossings of a common feature Y plane; normalized arclength inside each interval','bottom_plane_regularization_mm':.003,'removed_transverse_alignment_groove':{'y_bounds_mm':[31.851,33.149],'connector_z_bounds_mm':[-4.97,-4.32],'method':'join measured lower closed-end dovetail contours across the transverse notch without changing their mating outline'}},
        'upper_tracks':{'center_x':[-45.4819,45.48095],'width':7.5,'side_bevel':.4,'bottom_yz':np.round(curve,5).tolist()},
        'features':features}
    OUT.write_text(json.dumps(payload,separators=(',',':'))+'\n')
    print(OUT)

if __name__=='__main__':main()
