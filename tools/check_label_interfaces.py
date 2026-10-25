"""Conservative native label-envelope/recess checks; no physical fit claim."""
import argparse
from pathlib import Path

from build123d import Face, Solid

from vault._build import source_digest, source_hashes, write_json
from vault.exports import precise_volume
from vault.facade import build_facade
from vault.label import facade_transform, label_outline, to_facade
from vault.reference import PROJECT_ROOT
from vault.spec import ModuleSpec


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=PROJECT_ROOT/'out/reviews/label-interfaces.json')
    args = parser.parse_args(argv)
    cases = []
    for family,height in [(family,height) for family in ('S','M','L') for height in (1,2)]:
        # A solid envelope conservatively includes every hollow or solid label.
        # Check actual width and endpoints as well as clearance: an S label
        # would also clear a larger recess, without fulfilling that size.
        envelope = to_facade(Solid.extrude(Face(label_outline(family=family)),(0,0,2)),family)
        expected_width = {'S':47.,'M':91.6,'L':129.4}[family]
        bounds = envelope.bounding_box()
        width_passed = (abs(bounds.size.X-expected_width) < 1e-5
                        and abs(bounds.min.X-32.3) < 1e-5
                        and abs(bounds.max.X-(32.3+expected_width)) < 1e-5)
        facade = build_facade(spec=ModuleSpec(family,4,height))
        common = envelope.intersect(facade)
        overlap = sum(abs(precise_volume(s)) for s in common) if common else 0.
        distance = envelope.distance_to(facade)
        passed = (width_passed and envelope.is_valid and len(envelope.solids()) == 1
                  and overlap < 1e-6 and .0099 <= distance <= .0101)
        result = {'family':family,'height_units':height,'passed':passed,
                  'expected_label_width_mm':expected_width,'actual_label_width_mm':bounds.size.X,
                  'width_and_endpoints_passed':width_passed,
                  'label_bounds_mm':[list(bounds.min),list(bounds.max)],
                  'facade_transform':facade_transform(family),
                  'intersection_mm3':overlap,'minimum_clearance_mm':distance}
        print(result,flush=True)
        cases.append(result)
    report = {'schema':'vault-label-interface/v2','passed':all(c['passed'] for c in cases),
              'source_hash':source_digest(source_hashes(PROJECT_ROOT)),
              'face_normal_in_assembly':[0,1,0],
              'text_up_in_assembly':[0,0,1], 'cases':cases,
              'limits':'Native envelope/recess clearance only. Adhesive attachment, printer fit, and retention are untested.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_json(args.output,report)
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
