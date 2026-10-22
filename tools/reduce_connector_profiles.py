"""Remove redundant connector sections with a bounded interpolation error.

Run after measure_connectors.py to reduce the freshly measured profile data.
The surviving XY points and landmark parameters are retained exactly. This
reduces native surface count without fitting new curves to the mating profiles.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


DEFAULT_DATA = Path(__file__).resolve().parents[1] / 'research/legacy_profiles/connector_profiles.json'


def reduce_sections(feature, tolerance):
    sections = feature['sections']
    heights = np.asarray([section['z'] for section in sections])
    parameters = np.unique(np.concatenate([section['parameters'] for section in sections]))
    curves = []
    for section in sections:
        closed = np.vstack((section['points'], section['points'][0]))
        curves.append(np.column_stack([
            np.interp(parameters, section['parameters'], closed[:, axis]) for axis in range(2)
        ]))
    curves = np.asarray(curves)

    # Preserve crown and skin root caps, their adjoining stations, and the
    # stable detent shoulder used by native planar-contact assembly.
    required = {0, 1, len(sections) - 2, len(sections) - 1}
    if feature['name'].startswith('lower_open_end_detent_'):
        required.update(i for i, z in enumerate(heights) if abs(z + 4.5) < 1e-9)
    keep = set(required)
    ordered = sorted(required)
    pending = list(zip(ordered, ordered[1:]))
    maximum_error = 0.0
    while pending:
        first, last = pending.pop()
        if last - first < 2:
            continue
        fractions = (heights[first + 1:last] - heights[first]) / (heights[last] - heights[first])
        expected = curves[first][None] + fractions[:, None, None] * (curves[last] - curves[first])[None]
        errors = np.max(np.linalg.norm(curves[first + 1:last] - expected, axis=2), axis=1)
        worst = int(np.argmax(errors))
        error = float(errors[worst])
        if error > tolerance:
            middle = first + 1 + worst
            keep.add(middle)
            pending.extend(((first, middle), (middle, last)))
        else:
            maximum_error = max(maximum_error, error)

    result = {**feature, 'sections': [sections[index] for index in sorted(keep)]}
    report = {
        'name': feature['name'],
        'original_sections': len(sections),
        'retained_sections': len(keep),
        'maximum_pointwise_xy_error_mm': maximum_error,
        'preserved_datum_z_mm': [float(heights[index]) for index in sorted(required)],
    }
    return result, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--output', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--tolerance', type=float, default=0.04)
    args = parser.parse_args()
    if not np.isfinite(args.tolerance) or args.tolerance <= 0:
        parser.error('--tolerance must be positive and finite')
    payload = json.loads(args.source.read_text())
    if 'section_reduction' in payload['measurement']:
        parser.error('Input is already reduced; rerun measure_connectors.py before reducing again')

    features, reports = [], []
    for feature in payload['features']:
        reduced, report = reduce_sections(feature, args.tolerance)
        features.append(reduced)
        reports.append(report)
        print(f"{report['name']}: {report['original_sections']} -> {report['retained_sections']}", flush=True)
    payload['features'] = features
    payload['measurement']['section_reduction'] = {
        'tolerance_mm': args.tolerance,
        'original_section_count': sum(report['original_sections'] for report in reports),
        'retained_section_count': sum(report['retained_sections'] for report in reports),
        'maximum_pointwise_xy_error_mm': max(report['maximum_pointwise_xy_error_mm'] for report in reports),
        'method': 'Recursive station selection evaluated at every original height and the union of all contour knots. Piecewise-linear interpolation makes the pointwise XY displacement bound apply between these samples as well.',
        'preservation': 'Surviving section points and landmark parameters are unchanged. First and last two stations and detent shoulder stations are mandatory.',
        'features': reports,
    }
    args.output.write_text(json.dumps(payload, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
