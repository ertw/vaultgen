"""Native slide-to-box registration after removing sacrificial channel sheets."""
import json

from build123d import Axis

from vault.box import BoxSpec, _runner_support, build_box
from vault.drawer import DrawerLayout
from vault.reference import PROJECT_ROOT
from vault.runner_slides import RunnerSlideSpec, build_runner_slide


def main():
    report = {'schema': 'vault-runner-slides-box-fit/v1', 'units': 'mm',
              'method': 'Native B-rep intersections and minimum surface distances. '
                        'Only the explicitly removable box channel supports are subtracted.',
              'registration': 'For side +/-1: rotate slide about Y by -side*90 degrees, '
                              'then translate by (side*(73.9+family_width_delta),28.1,23.5+tier).',
              'cases': []}
    for family, depth, height in [('S', 4, 1), ('M', 3, 1), ('L', 7, 2)]:
        box_spec = BoxSpec(family, depth, height)
        layout = DrawerLayout(box_spec)
        box = build_box(spec=box_spec)
        for side in (-1, 1):
            for tier in layout.spec.tier_offsets:
                support = _runner_support(side, .3, layout=layout, tier=tier).translate((0, 2.3, -1))
                box = box.cut(support)
        slide = build_runner_slide(spec=RunnerSlideSpec(depth))
        for side in (-1, 1):
            for tier in layout.spec.tier_offsets:
                for withdrawal in (0, .1):
                    fitted = slide.rotate(Axis.Y, -side*90).translate(
                        (side*(73.9+layout.width_delta), 28.1+withdrawal, 23.5+tier))
                    intersection = box.intersect(fitted)
                    volume = sum(s.volume for s in intersection) if intersection else 0
                    clearance = box.distance_to(fitted)
                    case = {'configuration': f'{family}{depth} {height}F', 'side': side,
                            'tier_offset_mm': tier, 'withdrawal_mm': withdrawal,
                            'intersection_mm3': volume, 'clearance_mm': clearance,
                            'passed': volume < 1e-6 and (withdrawal == 0 or clearance > .015)}
                    report['cases'].append(case)
                    print(case, flush=True)
    report['passed'] = all(c['passed'] for c in report['cases'])
    report['limitations'] = ('Dry geometric fit only. Zero minimum distance at full insertion '
                            'is the intended rear stop contact. A 0.1 mm withdrawal checks the '
                            'small nominal radial seating clearance; printer fit must be checked.')
    path = PROJECT_ROOT / 'research/runner_slides_box_fit.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    if not report['passed']:
        raise SystemExit('Runner slide / box fit audit failed')


if __name__ == '__main__':
    main()
