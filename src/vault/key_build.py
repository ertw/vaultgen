"""Build and validate a single-piece key in immutable build storage."""

import argparse
import hashlib
import json
from pathlib import Path

from ._build import run_build
from .project import PROJECT_ROOT
from .build_events import stage


PRINT_NOTE = (
    "Print one complete key per drawer, with the gear bottom on the build plate. "
    "Check overhangs in the slicer and test printed fit before use."
)


def _export_key(output, spec):
    from .exports import export_part_set
    from .key import build_key_parts

    with stage('construction'):
        parts = build_key_parts()
    return export_part_set(output, spec, parts,
                           kind='key', print_note=PRINT_NOTE)


def build_key(output: Path):
    from .key import KeySpec

    spec = KeySpec()
    configuration = {'part': spec.slug, 'construction': 'single_piece'}
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    return run_build(
        PROJECT_ROOT, digest, lambda state: _export_key(state.stage, spec),
        parameters=configuration, output=Path(output), aliases=[f'latest/{spec.slug}'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'out',
                        help='immutable build output directory (default: out)')
    args = parser.parse_args(argv)
    build_key(args.output)


if __name__ == '__main__':
    main()
