"""Run a generator job outside the HTTP process, retaining checked exports."""
import argparse
import json
from pathlib import Path

from .generator import Configuration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    config = Configuration.parse(json.loads(args.configuration))
    from .__main__ import build, select_spec
    from ._build import source_hashes, source_digest, verify_files
    from .reference import PROJECT_ROOT
    digest = source_digest(source_hashes(PROJECT_ROOT))
    builds = []
    for part in config.parts:
        if source_digest(source_hashes(PROJECT_ROOT)) != digest:
            raise RuntimeError('Generator source changed during this set. Generate again to use one revision.')
        spec = select_spec(part, config.family, config.depth_units, config.height_units)
        print(f'Preparing {spec.name}', flush=True)
        previous = args.output / 'latest' / spec.slug
        reused = False
        if previous.is_dir():
            try:
                manifest = verify_files(previous)
                reused = manifest['source_hash'] == digest
            except (ValueError, RuntimeError, KeyError, OSError):
                pass
        if reused:
            destination = previous.resolve()
            print(f'Reusing checked build {destination.name}', flush=True)
        else:
            destination = build(args.output, spec)
        builds.append(destination.name)
        # A failed later part never hides earlier, successfully checked exports.
        args.receipt.write_text(json.dumps(builds))
    if source_digest(source_hashes(PROJECT_ROOT)) != digest:
        raise RuntimeError('Generator source changed during this set. Generate again to use one revision.')
    print('All requested parts passed their export checks.', flush=True)


if __name__ == '__main__':
    main()
