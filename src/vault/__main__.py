"""Build, export, render, and measure the reconstruction."""
from __future__ import annotations

import argparse
from pathlib import Path

from .build import build, build_preview, select_spec, selected_build
from .project import PROJECT_ROOT
from .spec import DEFAULT_SPEC, FAMILIES, NEW_PATTERN_CONSTRUCTION, ModuleSpec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate', 'render'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--part', choices=['module', 'facade', 'box', 'rails', 'runner_guides', 'runner_slides', 'key', 'spring', 'runner_stop', 'facade_cap', 'key_cap', 'latch'], default='module')
    parser.add_argument('--family', choices=FAMILIES, default='S')
    parser.add_argument('--depth-units', type=int, default=4)
    parser.add_argument('--height-units', type=int, default=1)
    parser.add_argument('--box-variant', choices=('plain', 'gridfinity'), default='plain',
                        help='Plain drawer floor or integral Gridfinity pockets')
    parser.add_argument('--box-rear-pattern', choices=('plain', 'waffle', 'miura'), default='plain',
                        help='Plain box rear or a two-perimeter corrugated waffle/Miura rear wall')
    parser.add_argument('--box-floor', type=float, choices=(0., .8, 3.), default=.8,
                        help='Box floor thickness in mm; 0 selects Floorless and requires --box-variant gridfinity')
    parser.add_argument('--facade-floor', choices=('0.8', 'default'), default='default',
                        help='0.8 mm shelled facade floor or the default rear pocket structure')
    parser.add_argument('--drawer-columns', type=int, choices=(1, 2), default=1,
                        help='Two columns create an L² module for two S drawers (family L only)')
    parser.add_argument('--drawer-rows', type=int, choices=(1, 2), default=1,
                        help='Two rows with two columns create four S1F drawers in an L 2F module')
    parser.add_argument('--wall-pattern', choices=('plain', 'waffle', 'miura'), default='plain')
    parser.add_argument('--pattern-construction', choices=('recessed', 'corrugated'), default=NEW_PATTERN_CONSTRUCTION,
                        help='Thin corrugated wall (default) or outer-only recesses inside the original wall envelope')
    parser.add_argument('--pattern-pitch', type=float, default=14.0, help='Pattern cell pitch, 8–40 mm')
    parser.add_argument('--pattern-depth', type=float, default=1.7, help='Pattern relief within the existing wall, 0.2–2 mm')
    parser.add_argument('--pattern-line-width', type=float, default=0.65,
                        help='Target extrusion width for two perimeters with a 0.6 mm nozzle, 0.6–1 mm')
    parser.add_argument('--pattern-faces', choices=('all', 'sides'), default='all',
                        help='Pattern all four long sleeve faces, or just the left/right sides')
    parser.add_argument('--samples', type=int, default=100_000, help='Area samples and maximum vertex samples per direction')
    parser.add_argument('--tolerance', type=float, default=.25, help='Maximum retained-surface sample deviation in mm, including the simplified outside corners')
    parser.add_argument('--mating-tolerance', type=float, default=.1, help='Stricter maximum deviation in the mechanical interface regions, in mm')
    args = parser.parse_args()
    if args.box_floor == 0 and args.box_variant != 'gridfinity':
        parser.error('A floorless box requires --box-variant gridfinity')
    try:
        spec = ModuleSpec(args.family, args.depth_units, args.height_units,
                          drawer_columns=args.drawer_columns, drawer_rows=args.drawer_rows,
                          wall_pattern=args.wall_pattern, pattern_pitch=args.pattern_pitch,
                          pattern_depth=args.pattern_depth, pattern_line_width=args.pattern_line_width,
                          pattern_faces=args.pattern_faces, pattern_construction=args.pattern_construction)
    except ValueError as error:
        parser.error(str(error))
    try:
        spec = select_spec(args.part, args.family, args.depth_units, args.height_units,
                           box_variant=args.box_variant, box_floor=args.box_floor,
                           box_rear_pattern=args.box_rear_pattern,
                           facade_floor=.8 if args.facade_floor == '0.8' else 'default',
                           drawer_columns=args.drawer_columns, drawer_rows=args.drawer_rows,
                           wall_pattern=args.wall_pattern, pattern_pitch=args.pattern_pitch,
                           pattern_depth=args.pattern_depth, pattern_line_width=args.pattern_line_width,
                           pattern_faces=args.pattern_faces, pattern_construction=args.pattern_construction)
    except ValueError as error:
        parser.error(str(error))
    if args.output is None:
        args.output = PROJECT_ROOT / 'out'
    if args.samples < 1 or args.tolerance <= 0 or args.mating_tolerance <= 0:
        parser.error('Samples and tolerance must be positive')
    if args.command == 'build':
        build(args.output, spec)
        return
    selected = selected_build(args.output, spec)
    review_root = selected.parent.parent if selected.parent.name == 'builds' else args.output
    review = review_root / 'reviews' / selected.name if (selected / 'manifest.json').is_file() else selected / 'review'
    review.mkdir(parents=True, exist_ok=True)
    model_path = selected / f'{spec.slug}.step'
    if not model_path.is_file():
        model_path = selected / f'{spec.slug}_model.stl'
    if args.command == 'render':
        from .render import render_review
        from .tessellation import load_model
        render_review(load_model(model_path), review)
    else:
        if spec != DEFAULT_SPEC:
            parser.error('The full source comparison currently supports S4 1F; other sizes need their own source registration.')
        from .validation import compare
        result = compare(model_path, review / 'comparison.json',
                         args.samples, args.tolerance, args.mating_tolerance)
        for direction in ['reference_to_model', 'model_to_reference']:
            row = result[direction]
            print(f"{direction}: p95={row['p95_mm']:.4f}, p99={row['p99_mm']:.4f}, max={row['max_mm']:.4f} mm; {row['fraction_within_tolerance']:.2%} within {args.tolerance} mm")
        for name, directions in result['mating_regions'].items():
            maximum = max(row['max_mm'] for row in directions.values())
            print(f"{name}: sampled max={maximum:.4f} mm (limit {args.mating_tolerance:g} mm)")
        if not result['within_sampled_tolerance']:
            raise SystemExit('Surface comparison exceeds the requested tolerance. See comparison.json for locations.')


if __name__ == '__main__':
    main()
