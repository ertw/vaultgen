"""Sample rigid insertion and rotation of the recessed, plain-head cam screw.

No elastic-contact exemptions or fit coupons: this is preview geometry only.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from build123d import Axis

from vault.exports import precise_volume
from vault.printed_joint import (
    D,
    build_printed_box, build_printed_facade, build_printed_screw,
)
from vault.reference import PROJECT_ROOT


VOLUME_TOLERANCE = 1e-5


def intersection_volume(a, b):
    """Positive common solid volume; touching faces/edges contribute nothing."""
    return sum(abs(precise_volume(solid))
               for piece in (a.intersect(b) or []) for solid in piece.solids())


def axial_clearance(moving, fixed, sign, limit=2.0):
    """Bracket the first nearby axial contact to 0.001 mm using native solids."""
    if intersection_volume(moving.translate((0, sign*limit, 0)), fixed) <= VOLUME_TOLERANCE:
        raise ValueError('The expected axial retaining surface did not stop the screw')
    low, high = 0.0, limit
    while high-low > .001:
        middle = (low+high)/2
        if intersection_volume(moving.translate((0, sign*middle, 0)), fixed) > VOLUME_TOLERANCE:
            high = middle
        else:
            low = middle
    return {'free_mm': low, 'blocked_mm': high}


def inspect_joint(box=None, facade=None, d=D, step_degrees=5):
    box = build_printed_box(d) if box is None else box
    facade = build_printed_facade(d) if facade is None else facade
    front = facade.translate((0,d.facade_seat,0))
    template = build_printed_screw(d)
    def pose(x,angle):
        return template.rotate(Axis.Y,angle).translate((x,d.entry_head_y+d.lead*angle/360,d.axis_z))
    result={'rotation': [], 'insertion': [], 'wrong_entry': []}
    for x in (-d.axis_x,d.axis_x):
        for angle in [*range(0,int(d.turn),step_degrees),d.turn]:
            screw=pose(x,angle)
            result['rotation'].append({'x':x,'angle':angle,
                'box_mm3':intersection_volume(screw,box),
                'facade_mm3':intersection_volume(screw,front)})
        for retreat in range(0,18):
            screw=pose(x,0).translate((0,-retreat,0))
            result['insertion'].append({'x':x,'retreat':retreat,
                'box_mm3':intersection_volume(screw,box),
                'facade_mm3':intersection_volume(screw,front)})
        for angle in (90,180,270):
            wrong=pose(x,0).rotate(Axis((x,0,d.axis_z),(0,1,0)),angle)
            result['wrong_entry'].append({'x':x,'angle':angle,
                'blocked_mm3':intersection_volume(wrong,box)+intersection_volume(wrong,front)})
    result['checks']={
      'clear_rotation':all(max(p['box_mm3'],p['facade_mm3'])<1e-5 for p in result['rotation']),
      'clear_insertion':all(max(p['box_mm3'],p['facade_mm3'])<1e-5 for p in result['insertion']),
      'keyed_entry':all(p['blocked_mm3']>.01 for p in result['wrong_entry']),
      'closed_stop':intersection_volume(pose(d.axis_x,d.turn+10),front)>.01,
      'head_inside_wall':d.locked_head_y-d.head_thickness >= d.box_seat,
      'facade_seats':intersection_volume(box,front)<1e-5,
    }
    locked=pose(d.axis_x,d.turn)
    result['axial_clearance']={'thread_pullout':axial_clearance(locked,front,-1),
                                'head_seat':axial_clearance(locked,box,1)}
    result['checks']['head_inside_at_axial_limit']=(
        d.locked_head_y-d.head_thickness-result['axial_clearance']['thread_pullout']['free_mm']
        >= d.box_seat-.001)
    result['passed']=all(result['checks'].values())
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=PROJECT_ROOT/'out/reviews/printed-joint-recessed')
    parser.add_argument('--step-degrees',type=int,default=5)
    args=parser.parse_args()
    if not 1<=args.step_degrees<=30:parser.error('Step must be 1–30 degrees')
    report=inspect_joint(step_degrees=args.step_degrees)
    report['dimensions']=asdict(D)
    report['source_sha256']={str(p.relative_to(PROJECT_ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [PROJECT_ROOT/'src/vault/printed_joint.py',PROJECT_ROOT/'src/vault/box.py',PROJECT_ROOT/'src/vault/facade.py']}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'joint_check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['checks'],indent=2),flush=True)
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
