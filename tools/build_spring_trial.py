"""Build the isolated, one-loop-removed spring trial through checked storage.

Run from the repository root after sourcing .local-env::

    python tools/build_spring_trial.py

The trial is deliberately outside the generator catalog and normal spring
history. It keeps its own immutable builds under out/experiments/.
"""
from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path

from build123d import Plane, Solid

from vault._build import run_build, verify_files, write_json
from vault.accessories import build_spring
from vault.exports import export_part_set, precise_volume
from vault.project import PROJECT_ROOT
from vault.spring_trial import (
    BOSS_CENTER_X, BOSS_RADIUS, build_spring_trial, flexible_region,
)


@dataclass(frozen=True)
class TrialSpec:
    slug: str = 'spring_one_less_loop'
    name: str = 'Spring trial — one loop removed for a circular boss'


def overlap_volume(left, right):
    common = left.intersect(right)
    return sum(abs(precise_volume(s)) for s in common.solids()) if common else 0.0


def clearance_report(spring, original):
    # Registration comes from the native circular fork, not print-mesh bounds.
    # A full-height cylinder conservatively includes the circular boss's foot.
    boss = Solid.make_cylinder(BOSS_RADIUS, 5.155,
                               Plane(origin=(BOSS_CENTER_X, 0, 0)))
    overlap = overlap_volume(spring, boss)
    flexure_gap = flexible_region(spring).distance_to(boss)
    original_gap = flexible_region(original).distance_to(boss)
    report = {
        'schema': 'vault-spring-trial-clearance/v1', 'units': 'mm',
        'boss_center_in_spring_frame': [BOSS_CENTER_X, 0, 0],
        'boss_radius_mm': BOSS_RADIUS, 'boss_height_mm': 5.155,
        'full_boss_overlap_mm3': overlap,
        'whole_spring_minimum_boss_gap_mm': spring.distance_to(boss),
        'flexure_minimum_boss_gap_mm': flexure_gap,
        'original_flexure_minimum_boss_gap_mm': original_gap,
        'original_volume_mm3': precise_volume(original),
        'trial_volume_mm3': precise_volume(spring),
        'passed': overlap < 1e-6 and flexure_gap > 3.0,
        'limits': 'Undeformed native geometry only. Fork seating remains nominal '
                  'and intentionally close to the boss; the flexure gap excludes '
                  'that mounting fork. No spring-force, deflection, fatigue, '
                  'installation, or printed-fit qualification.',
    }
    if not report['passed']:
        raise ValueError(f'Circular-boss clearance failed: {report}')
    return report


def draw_comparison(original, spring, path):
    """Top view of actual native bed outlines with the circular boss fixture."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon

    fig, ax = plt.subplots(figsize=(9, 7))
    for shape, color, alpha, label in (
            (original, '#a2a7ae', .45, 'Original spring'),
            (spring, '#2276a7', .85, 'Trial: nearest loop removed')):
        bed = max((face for face in shape.faces()
                   if abs(face.bounding_box().min.Z) < 1e-5
                   and abs(face.bounding_box().max.Z) < 1e-5), key=lambda f: f.area)
        wire = bed.outer_wire()
        points = [wire.position_at(i / 1600) for i in range(1601)]
        ax.add_patch(Polygon([(p.X, p.Y) for p in points], closed=True,
                             facecolor=color, edgecolor=color, alpha=alpha, label=label))
    ax.add_patch(Circle((BOSS_CENTER_X, 0), BOSS_RADIUS, facecolor='#efac4b',
                        edgecolor='#995b0c', alpha=.65, label='Full circular boss (13.6 mm)'))
    ax.set(xlim=(-26, 26), ylim=(-21, 21), aspect='equal',
           xlabel='X (mm)', ylabel='Y (mm)', title='One-off spring trial — flat print view')
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.10), frameon=False)
    ax.grid(alpha=.12)
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches='tight')
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=PROJECT_ROOT / 'out/experiments/spring-one-less-loop')
    args = parser.parse_args()
    spec = TrialSpec()
    configuration = {'part': spec.slug, 'experimental': True,
                     'omitted_loop': 'nearest upper loop beside mounting boss',
                     'boss_radius_mm': BOSS_RADIUS}
    print_note = ('Print flat in the supplied orientation. One-off trial with the '
                  'loop nearest the mounting boss removed; original contact tip, '
                  'fork and thickness profile retained. Install with the original '
                  'flat-side-up orientation. Fewer loops can increase stiffness; '
                  'test movement and return force before repeated use.')

    def generate(state):
        spring, original = build_spring_trial(), build_spring()
        report = clearance_report(spring, original)
        metadata, viewer = export_part_set(
            state.stage, spec, {spec.slug + '_single': spring},
            kind='spring_trial', print_note=print_note)
        write_json(state.stage / 'clearance.json', report)
        (state.stage / 'PRINTING.txt').write_text(print_note + '\n\n' + report['limits'] + '\n')
        draw_comparison(original, spring, state.stage / 'review/clearance.png')
        return {**metadata, 'experimental': True, 'clearance': report}, viewer

    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    destination = run_build(
        PROJECT_ROOT, digest, generate, parameters=configuration, output=args.output,
        inputs={'trial-builder.py': Path(__file__).resolve()},
        aliases=[f'latest/{spec.slug}'])
    verify_files(destination)


if __name__ == '__main__':
    main()
