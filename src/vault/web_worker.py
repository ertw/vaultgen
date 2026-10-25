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
    from ._build import source_hashes, source_digest, verify_files, git_provenance
    from .reference import PROJECT_ROOT
    digest = source_digest(source_hashes(PROJECT_ROOT))
    builds = []
    for part in config.parts:
        if source_digest(source_hashes(PROJECT_ROOT)) != digest:
            raise RuntimeError('Generator source changed during this set. Generate again to use one revision.')
        spec = select_spec(part, config.family, config.depth_units, config.height_units,
                           box_floor=config.box_floor, module_rear=config.module_rear)
        print(f'Preparing {spec.name}', flush=True)
        previous = args.output / 'latest' / spec.slug
        reused = False
        if previous.is_dir():
            try:
                manifest = verify_files(previous)
                current = git_provenance(PROJECT_ROOT)
                reused = (manifest['source_hash'] == digest and current is not None
                          and not current['dirty'] and manifest.get('git') == current)
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
    if config.part == 'set':
        from build123d import import_step
        from .assembly_validation import validate_assembly, validation_signature
        components = {}
        for kind, build_id in zip(config.parts, builds):
            directory = args.output / 'builds' / build_id
            manifest = verify_files(directory)
            for details in manifest['parts'].values():
                metadata = details.get('assembly_mesh') or {}
                relative = metadata.get('step_path', '')
                path = directory / relative
                if (metadata.get('schema') != 'vault-assembly-mesh/v1'
                        or metadata.get('coordinates') != 'native' or metadata.get('finished') is not True
                        or not relative or not path.resolve().is_relative_to(directory.resolve())
                        or relative not in manifest['checksums']):
                    raise RuntimeError('Missing finished assembly geometry; generate all parts again.')
                components[kind, metadata['component']] = import_step(path)
        print('Checking assembled component alignments and intersections…', flush=True)
        validation = validate_assembly(config, components=components,
                                       progress=lambda message: print(message, flush=True))
        if source_digest(source_hashes(PROJECT_ROOT)) != digest:
            raise RuntimeError('Generator source changed during assembly validation. Generate again.')
        record = {'validation_signature': validation_signature(config),
                  'configuration': config.as_dict(), 'build_ids': builds, 'validation': validation}
        destination = args.output / 'web' / 'assemblies'
        destination.mkdir(parents=True, exist_ok=True)
        temporary = destination / (args.receipt.stem + '.tmp')
        temporary.write_text(json.dumps(record, indent=2))
        temporary.replace(destination / (args.receipt.stem + '.json'))
        if not validation['passed']:
            failures = {key: [item for item in validation.get(key, []) if not item.get('passed')]
                        for key in ('solids', 'pairs', 'mating')}
            print(json.dumps({'assembly_fit_failures': failures}, indent=2), flush=True)
            raise RuntimeError('Assembly fit checks failed. Individual exports remain available; inspect the assembly warnings and validation report.')
    print('All requested parts passed their export checks.', flush=True)


if __name__ == '__main__':
    main()
