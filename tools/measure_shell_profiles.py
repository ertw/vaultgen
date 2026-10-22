"""Regenerate editable shell profiles from the purchased reference mesh.

This offline measurement tool is never imported by the native model. Outside
profiles preserve sharp skin, chamfer, and ear junctions, then simplify depth
stations within 0.05 mm. Coordinates are rounded to 0.001 mm so the resulting
CAD does not reproduce insignificant source triangulation noise.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from vault.reference import SOURCE, SOURCE_ORIGIN, load_reference

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path,
                    default=Path(__file__).resolve().parents[1] / 'research/legacy_profiles/shell_profiles.json')
output = parser.parse_args().output
m = load_reference()
existing = set([0, 7, 8.1, 20, 42, 60, 75.632, 90, 100, 110, 118.9, 119, 119.5, 120, 120.5, 121, 121.5, 122, 122.5, 123, 123.5, 124, 124.5, 125.0, 125.5, 126.0, 126.5, 127.0, 127.5, 128.0, 128.5, 129.0, 129.5, 130.0, 130.5, 131.0, 131.5, 132.0, 132.5, 133.0, 133.5, 134.0, 134.5, 135.0, 135.5, 136.0, 136.5, 137.0, 137.5, 138.0, 138.5, 139.0, 139.5, 140, 170, 171, 171.1, 171.5, 172, 172.1, 172.5, 173, 173.1, 173.5, 174, 174.1, 174.5, 174.6, 174.7, 174.8, 174.9, 175.0, 175.1, 175.2, 175.3, 175.4, 175.5, 175.6, 175.7, 175.8, 175.9, 176.0, 176.0997, 176.1, 176.1002, 176.11, 180, 188.1])
ys = sorted({130.85, 119.1046, 119.1048} | existing | set(np.arange(119.25,139,.25).round(4)) | set(np.arange(170.25,176.1,.25).round(4)))

def rays(seg,c,angles):
 angles=np.deg2rad(angles);direction=np.column_stack((np.cos(angles),np.sin(angles)));edge=seg[:,1]-seg[:,0];offset=seg[:,0]-c
 den=direction[:,0,None]*edge[None,:,1]-direction[:,1,None]*edge[None,:,0];valid=abs(den)>1e-10;safe=np.where(valid,den,1)
 t=(offset[:,0]*edge[:,1]-offset[:,1]*edge[:,0])[None,:]/safe;u=(offset[None,:,0]*direction[:,1,None]-offset[None,:,1]*direction[:,0,None])/safe
 valid&=(t>0)&(u>=-1e-7)&(u<=1+1e-7);radius=np.max(np.where(valid,t,-np.inf),axis=1);p=c+radius[:,None]*direction
 low=p[:,1]<0;high=p[:,1]>47;p[low]=c+(-c[1]/direction[low,1])[:,None]*direction[low];p[high]=c+((47-c[1])/direction[high,1])[:,None]*direction[high]
 return p

def crossing(seg,axis,value,upper=True):
 a=seg[:,0];v=seg[:,1]-a;good=abs(v[:,axis])>1e-12;t=np.zeros(len(v));t[good]=(value-a[good,axis])/v[good,axis];q=a+t[:,None]*v;good&=(t>=-1e-6)&(t<=1+1e-6)
 candidates=q[good]
 if not len(candidates):return None
 return candidates[np.argmax(candidates[:,1-axis]) if upper else np.argmin(candidates[:,1-axis])]

measured=[]
for k,y in enumerate(ys):
 whole=trimesh.intersections.mesh_plane(m,[0,1,0],[0,max(.01,min(188.099,y)),0])[:,:,[0,2]]
 curves=[]
 for ci,(c,start) in enumerate([([67,12],-90),([67,35],0),([-67,35],90),([-67,12],180)]):
  c=np.array(c);right=c[0]>0;upper=c[1]>20
  selected=((whole[:,:,0].max(axis=1)>=67) if right else (whole[:,:,0].min(axis=1)<=-67)) & ((whole[:,:,1].max(axis=1)>=35) if upper else (whole[:,:,1].min(axis=1)<=12))
  seg=whole[selected];angles=list(np.linspace(start,start+90,25))
  def append_point(p):
   if p is None:return
   angle=np.degrees(np.arctan2(p[1]-c[1],p[0]-c[0]));angle+=360 if angle<start-1e-6 else 0
   angles.append(float(np.clip(angle,start+.0001,start+90-.0001)))
  for absolute_x in [81.4404,82.40025]:append_point(crossing(seg,0,absolute_x if right else -absolute_x,upper))
  # The exact nominal-skin intersection moves with the rounded front edge.
  for z in ([46.999] if upper else [.0012,.9612,1.0012]):
   append_point(crossing(seg,1,z,right))
  # The ear meets the original outside corner at a sharp re-entrant junction.
  dense_angles=np.linspace(start+.0001,start+90-.0001,901);dense=rays(seg,c,dense_angles)
  before=dense[4:-4]-dense[:-8];after=dense[8:]-dense[4:-4]
  turn=np.arctan2(before[:,0]*after[:,1]-before[:,1]*after[:,0],np.sum(before*after,axis=1))
  # Ignore quantization noise at the radial endpoints; a true junction has a
  # reproducible concave turn over an angular neighbourhood.
  best=int(np.argmin(turn))+4
  skin_fallback=(130.8<y<171 if upper else 136<y<171)
  fallback=(start+90-.02 if start in (-90,90) else start+.02)
  if skin_fallback:fallback=start+90-.02 if start in (0,180) else start+.02
  angles.append(float(dense_angles[best] if turn.min()<-.035 else fallback))
  if start==180:angles += [180.25,180.5,180.75,181,181.25,181.5,181.75,182,182.5]
  # Keep fixed vertex counts while preventing coincident wire vertices.
  angles=np.sort(angles)
  for j in range(1,len(angles)-1):
   angles[j]=max(angles[j],angles[j-1]+.01)
  for j in range(len(angles)-2,0,-1):
   angles[j]=min(angles[j],angles[j+1]-.01)
  pts=rays(seg,c,angles)
  if start==-90:pts[0]=[67,0];pts[-1]=[82.4004,12]
  if start==0:pts[0]=[82.4004,35];pts[-1]=[67,47]
  if start==90:pts[0]=[-67,47];pts[-1]=[-82.4004,35]
  if start==180:pts[0]=[-82.4004,12];pts[-1]=[-67,0]
  curves.append(np.round(pts,6).tolist())
 measured.append({'y':float(y),'corners':curves})
 if k%25==0:print('station',k,'/',len(ys),flush=True)

upper_skin_event = next(section for section in measured if section['y'] == 130.85)
sections = [section for section in measured if section['y'] != 130.85]
# Remove redundant near-coincident probes around the source's triangulation
# boundary. Retain a finite 0.05 mm transition at the sharp end of the ears.
sections=[s for s in sections if s['y'] not in (119.1046,176.1,176.1002)]
for section in sections:
 if section['y']==176.0997:section['y']=176.1
 if section['y']==176.11:section['y']=176.15
 for corner_index,curve in enumerate(section['corners']):
  points=np.array(curve)
  if corner_index==3:
   angles=np.degrees(np.arctan2(points[:,1]-12,points[:,0]+67));angles[angles<180]+=360
   remove={int(np.argmin(abs(angles-angle))) for angle in [180.25,180.5,180.75,181,181.25,181.5,181.75,182,182.5]}
   points=np.array([p for i,p in enumerate(points) if i not in remove])
  points=np.round(points,3)
  points[abs(abs(points[:,0])-82.4)<.001,0]=np.sign(points[abs(abs(points[:,0])-82.4)<.001,0])*82.4004
  points[abs(points[:,1])<.001,1]=0
  points[abs(points[:,1]-47)<.001,1]=47
  section['corners'][corner_index]=points.tolist()
ys=np.array([s['y'] for s in sections]);a=np.array([[q for c in s['corners'] for q in c] for s in sections])

def directed(p,q):
 v=np.roll(q,-1,axis=0)-q;w=p[:,None]-q[None];t=np.clip(np.sum(w*v[None],axis=-1)/np.maximum(np.sum(v*v,axis=-1),1e-20),0,1)
 return np.min(np.linalg.norm(w-t[:,:,None]*v[None],axis=-1),axis=1).max()

def error(p,q):return max(directed(p,q),directed(q,p))
keep={0,len(ys)-1}
def split(i,j):
 if j-i<2:return
 errors=[]
 for k in range(i+1,j):
  t=(ys[k]-ys[i])/(ys[j]-ys[i]);prediction=(1-t)*a[i]+t*a[j];errors.append(error(a[k],prediction))
 worst=int(np.argmax(errors))+i+1
 if max(errors)>.05:keep.add(worst);split(i,worst);split(worst,j)
split(0,len(ys)-1);stations=[s for k,s in enumerate(sections) if k in keep]

# Preserve the shallow left-lower ridge with one apex vertex. Its neighbours
# must retain wall/apex/regular-ray correspondence as the ridge fades out;
# simply sorting an added polar sample moves vertices between unrelated edges.
def left_corner_angle(point):
    return np.degrees(np.arctan2(point[1] - 12, point[0] + 67)) % 360

for station in stations:
    curve = np.array(station['corners'][3])
    center = np.array([-67., 12.])
    nominal_wall_x = -82.4004
    if station['y'] <= 119:
        segments = trimesh.intersections.mesh_plane(
            m, [0, 1, 0], [0, max(.01, station['y']), 0]
        )[:, :, [0, 2]]
        segments = segments[
            (segments[:, :, 0].min(axis=1) < -67)
            & (segments[:, :, 1].min(axis=1) < 12)
        ]
        vertices = segments.reshape(-1, 2)
        near_wall = vertices[(vertices[:, 1] > 10) & (vertices[:, 1] < 12)]
        apex = near_wall[near_wall[:, 0].argmin()]
        wall_vertices = near_wall[abs(near_wall[:, 0] - nominal_wall_x) < .00003]
        wall = wall_vertices[wall_vertices[:, 1].argmin()].copy()
        wall[0] = nominal_wall_x
        if apex[0] > nominal_wall_x - .02:
            # Continue the apex's measured height trend onto the original
            # smooth corner where the ridge has no appreciable outward rise.
            apex_z = min(11.4 + .00325 * station['y'], wall[1] - .05)
            apex_angle = 180 + np.degrees(np.arctan2(12 - apex_z, 15.4))
            apex = rays(segments, center, [apex_angle])[0]
        lower_wall = crossing(segments, 0, -82.40025, False)
        if not 183.76 < left_corner_angle(lower_wall) < 187.49:
            existing_edges = np.stack([curve[:-1], curve[1:]], axis=1)
            lower_wall = rays(existing_edges, center, [185.625])[0]
        angles = np.array([left_corner_angle(point) for point in curve])
        first_regular_ray = curve[np.argmin(abs(angles - 183.75))]
        assert abs(angles[4] - 187.5) < .01
        anchors = np.round([wall, apex, lower_wall], 3)
        on_wall = abs(anchors[:, 0] - nominal_wall_x) < .001
        anchors[on_wall, 0] = nominal_wall_x
        curve = np.vstack([
            curve[0], anchors[0], anchors[1], first_regular_ray,
            anchors[2], curve[4:]
        ])
    else:
        # A collinear midpoint preserves the later profiles exactly while
        # retaining the same vertex count for the ruled loft.
        curve = np.vstack([curve[:2], (curve[1] + curve[2]) / 2, curve[2:]])
    station['corners'][3] = curve.tolist()

# The rising upper shelf reaches the skin between the regular measurement
# stations. Keep that event explicit without changing the other corner lofts.
event_y = 130.85
depths = np.array([station['y'] for station in stations])
event_index = np.searchsorted(depths, event_y) - 1
fraction = (event_y - depths[event_index]) / (depths[event_index + 1] - depths[event_index])
event = {'y': event_y, 'corners': []}
for corner in range(4):
    before = np.array(stations[event_index]['corners'][corner])
    after = np.array(stations[event_index + 1]['corners'][corner])
    event['corners'].append(((1 - fraction) * before + fraction * after).tolist())
for corner in (1, 2):
    points = np.round(upper_skin_event['corners'][corner], 3)
    on_wall = abs(abs(points[:, 0]) - 82.4) < .001
    points[on_wall, 0] = np.sign(points[on_wall, 0]) * 82.4004
    points[abs(points[:, 1] - 47) < .001, 1] = 47
    event['corners'][corner] = points.tolist()
stations.insert(event_index + 1, event)

# Keep the outer-wall/skin corner at the same loft index through the mouth.
# Common heights prevent moving sharp corners from creating diagonal wedges.
# Derive a compact height schedule from the existing end profile and retain
# the moving ear/curve junction as a semantic anchor at each station.
def simplify_corner(points, count):
    while len(points) > count:
        start, end, point = points[:-2], points[2:], points[1:-1]
        delta = end - start
        parameter = np.clip(
            np.sum((point - start) * delta, axis=1) / np.sum(delta * delta, axis=1),
            0, 1
        )
        errors = np.linalg.norm(point - start - parameter[:, None] * delta, axis=1)
        points = np.delete(points, int(errors.argmin()) + 1, axis=0)
    return points

reference = next(station for station in stations if station['y'] == 170.75)
for corner in (1, 2):
    baseline = np.array(reference['corners'][corner])
    end = np.array(stations[-1]['corners'][corner])
    if corner == 2:
        baseline, end = baseline[::-1], end[::-1]
    skin_index = np.flatnonzero(baseline[:, 1] == 47)[0]
    fractions = (baseline[skin_index:, 0] - baseline[skin_index, 0]) / (
        baseline[-1, 0] - baseline[skin_index, 0]
    )
    end = end[:np.flatnonzero(end[:, 1] == 47)[0] + 1]
    reference_heights = simplify_corner(end, skin_index + 1)[:, 1]
    for station in stations:
        if station['y'] < 170.75:
            continue
        curve = np.array(station['corners'][corner])
        if corner == 2:
            curve = curve[::-1]
            curve[:, 0] *= -1
        first_skin = np.flatnonzero(curve[:, 1] == 47)[0]
        wall_x = curve[first_skin, 0]
        heights = reference_heights.copy()
        if wall_x > 68:
            near_wall = np.flatnonzero(curve[:first_skin + 1, 0] < wall_x + .02)
            junction_z = curve[int(near_wall[0]), 1]
            if 35.1 < junction_z < 46.95:
                index = int(np.argmin(abs(heights[1:-1] - junction_z))) + 1
                heights[index] = junction_z
        heights.sort()
        segments = np.stack([curve[:-1], curve[1:]], axis=1)
        start = segments[:, 0]
        delta = segments[:, 1] - start
        boundary = []
        for height in heights:
            if height == 47:
                x = wall_x
            else:
                valid = abs(delta[:, 1]) > 1e-12
                parameter = np.zeros(len(delta))
                parameter[valid] = (height - start[valid, 1]) / delta[valid, 1]
                valid &= (parameter >= -1e-7) & (parameter <= 1 + 1e-7)
                x = (start + parameter[:, None] * delta)[valid, 0].max()
            boundary.append([x, height])
        boundary = np.array(boundary)
        skin = np.column_stack([
            wall_x + fractions * (67 - wall_x), np.full(len(fractions), 47)
        ])
        curve = np.vstack([boundary[:-1], skin])
        if corner == 2:
            curve[:, 0] *= -1
            curve = curve[::-1]
        station['corners'][corner] = curve.tolist()

# central retention recess lower contour; sample ray/lower vertical intersection at y180
seg=trimesh.intersections.mesh_plane(m,[0,1,0],[0,180,0])[:,:,[0,2]]
groove=[]
for x in np.linspace(-10.4,10.4,65):
 a=seg[:,0];v=seg[:,1]-a;good=abs(v[:,0])>1e-12;t=np.zeros(len(v));t[good]=(x-a[good,0])/v[good,0]
 z=a[:,1]+t*v[:,1];good&=(t>=-1e-7)&(t<=1+1e-7)&(z>.5)&(z<4)
 groove.append([round(x,5),round(z[good].max(),5)])
# Rear ramp has a different, shallower curve than the deep retention recess.
seg=trimesh.intersections.mesh_plane(m,[0,1,0],[0,182.6003,0])[:,:,[0,2]]
ramp=[]
for x in np.linspace(-10.4,10.4,65):
 a=seg[:,0];v=seg[:,1]-a;good=abs(v[:,0])>1e-12;t=np.zeros(len(v));t[good]=(x-a[good,0])/v[good,0]
 z=a[:,1]+t*v[:,1];good&=(t>=-1e-7)&(t<=1+1e-7)&(z>.5)&(z<4)
 ramp.append([round(float(x),6),round(float(z[good].max()-.0003),6)])
# Opposed mouth hook relief: measured YZ sections across the positive-X pocket.
# Only these small retained functional blends need tabulated measurements.
y_values=182.3001+(1-np.cos(np.linspace(0,np.pi,49)))*2.5
all_pockets={}
for side in (1,-1):
 pockets=[]
 for x in [67.65,68,68.5,69,69.19,69.2,69.5,70,70.5,71,72,73,74,74.8,75.0264,75.3,75.6,75.8,75.9,76,76.02,76.05]:
  seg=trimesh.intersections.mesh_plane(m,[1,0,0],[side*x,0,0])[:,:,[1,2]]
  if side<0:seg[:,:,1]=47.002815-seg[:,:,1]
  lower=[];upper=[]
  for y in y_values:
   probe=max(182.3003,min(187.2999,y))
   a=seg[:,0];v=seg[:,1]-a;good=abs(v[:,0])>1e-12;t=np.zeros(len(v));t[good]=(probe-a[good,0])/v[good,0]
   z=a[:,1]+t*v[:,1];good&=(t>=-1e-7)&(t<=1+1e-7)&(z>5)&(z<12)
   selected=z[good]
   bottom=min(selected) if len(selected) else 9.501408
   top=max(selected) if x<69.1904 else 11.6914
   lower.append([round(float(y),6),round(float(bottom),6)])
   upper.append([round(float(y),6),round(float(top),6)])
  pockets.append({'x':x,'lower':lower,'upper':upper})
 pockets.insert(0,dict(pockets[0],x=67.62))
 all_pockets['right' if side==1 else 'left']=pockets

data = {
    'description': 'Editable measured shell cross-sections and retained interior blends, in millimetres. Canonical X=width, Y=depth from the back, Z=height. Outside corners use ruled polylines with explicit skin, chamfer, and ear-junction anchors. Depth stations are simplified for a compact, robust native solid; no source mesh is required at runtime.',
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'source_file': SOURCE.name,
    'source_axis_order': [0, 2, 1],
    'source_origin_after_permutation': SOURCE_ORIGIN.tolist(),
    'measurement': {'outer_ray_angle_step_degrees': 3.75, 'outer_anchors': ['nominal skin intersection', '0.96/1.00 mm lower chamfer', 'outer wall', 'ear/original-curve junction', 'left lower ridge apex', 'fixed upper skin corner correspondence'], 'outer_measurement_station_step_mm': 0.25, 'outer_station_simplification_mm': 0.05, 'outer_coordinate_rounding_mm': 0.001, 'outer_anchor_minimum_separation_degrees': 0.01, 'outer_upper_skin_event_y_mm': 130.85, 'outer_end_transition_mm': 0.05, 'outer_sections_count': 81, 'profile_representation': 'Short polylines with measured sharp junctions; ruled lofts between simplified depth stations.', 'retention_curve_sample_spacing_mm': 0.325},
    'outer_sections': stations,
    'retention_recess': groove,
    'retention_ramp': ramp,
    'mouth_pocket_sections': all_pockets,
}
data['measurement']['outer_sections_count'] = len(stations)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(data, indent=2) + '\n')
print(f'Wrote {len(stations)} simplified outer sections to {output}')
