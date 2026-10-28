"""Sampled reference diagnostics and cap interface checks, not printed-fit proof."""
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from build123d import Axis
from vault.accessories import build_spring, build_runner_stop, build_facade_cap, build_key_cap
from vault.exports import precise_volume
from vault.latch import build_latch
from vault.tessellation import review_mesh
from vault.reference import PROJECT_ROOT


def main():
    rows = {}
    for name, build in [('Springs.stl',build_spring),('Runner Stopper.stl',build_runner_stop),
                        ('Facade Cap.stl',build_facade_cap),('Key Cap.stl',build_key_cap),('Latch.stl',build_latch)]:
        path=next((PROJECT_ROOT/'original_files').rglob(name))
        source=sorted(trimesh.load(path).split(),key=lambda m:m.volume,reverse=True)[0]
        origin=np.r_[source.bounds[:,:2].mean(axis=0),source.bounds[0,2]]
        source.apply_translation(-origin)
        if name=='Facade Cap.stl':
            source.vertices[:,2]=3.8-source.vertices[:,2]
            source.invert()
        native=review_mesh(build())
        distances={}
        for label,a,b in [('source_to_native',source,native),('native_to_source',native,source)]:
            pts=np.vstack([a.vertices,trimesh.sample.sample_surface(a,5000,seed=21)[0]])
            _,d,_=trimesh.proximity.closest_point(b,pts)
            distances[label]={'max_mm':float(d.max()),'p95_mm':float(np.percentile(d,95))}
        rows[name]={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'source_origin':origin.tolist(),'source_volume_mm3':float(source.volume),
                    'native_volume_mm3':float(native.volume),'sampled_deviation':distances}
        print(name,distances,flush=True)
    from vault.facade import build_facade
    from vault.key_geometry import build_handle_blank
    def overlap(a,b):
        common=a.intersect(b)
        return sum(abs(precise_volume(s)) for s in common) if common else 0.
    facade=build_facade()
    cap=build_facade_cap().rotate(Axis.X,90).translate((51.45,10,23.5))
    key_cap=build_key_cap().rotate(Axis.X,180).translate((0,0,35.517))
    checks={'facade_cap_overlap_mm3':overlap(facade,cap),
            'key_cap_overlap_mm3':overlap(build_handle_blank(),key_cap)}
    report={'limits':'Sampled deviations include regularized blends, intentional latch relief, the enlarged latch opening and rounded upper edges. No reference-equivalence or printed-fit acceptance is implied. Cap checks cover only the stated seated poses, not insertion or retention. Runner stop, spring and latch installation are not certified.',
            'latch_construction_sha256':hashlib.sha256((PROJECT_ROOT/'src/vault/latch.py').read_bytes()).hexdigest(),
            'construction_sha256':hashlib.sha256((PROJECT_ROOT/'src/vault/accessories.py').read_bytes()).hexdigest(),
            'parts':rows,'interfaces':checks}
    (PROJECT_ROOT/'research/accessories.json').write_text(json.dumps(report,indent=2)+'\n')
    print(checks)
    if any(v>1e-6 for v in checks.values()):raise SystemExit('Cap interface collision')

if __name__=='__main__':main()
