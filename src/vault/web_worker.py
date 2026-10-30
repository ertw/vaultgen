"""Run a generator task outside HTTP, retaining exact checked exports."""
import argparse
import json
import traceback
from pathlib import Path

from .build_events import emit, event_output, stage
from .generator import parse_configuration
from .spec import pattern_parameters, wall_parameters


def _write_receipt(path, value):
    """A scheduler must never observe a partially written result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, allow_nan=False))
    temporary.replace(path)


def _check_source(digest, *, assembly=False):
    from ._build import source_hashes, source_digest
    from .project import PROJECT_ROOT
    if source_digest(source_hashes(PROJECT_ROOT)) != digest:
        if assembly:
            raise RuntimeError('Generator source changed during assembly validation. Generate again.')
        raise RuntimeError('Generator source changed during this set. Generate again to use one revision.')


def _build_part(config, part, output, digest):
    from .build import build, select_spec
    from ._build import git_provenance
    from .build_cache import expected_for_spec, find_reusable
    from .project import PROJECT_ROOT

    _check_source(digest)
    if part == 'label':
        from .label_build import build_label
        spec, generate = config, build_label
    elif part == 'gridfinity_bins':
        from .bin_build import build_bins
        spec, generate = config, build_bins
    else:
        spec = select_spec(part, config.family, config.depth_units, config.height_units,
                           box_floor=config.box_floor, box_variant=config.box_variant,
                           box_rear_pattern=config.box_rear_pattern,
                           facade_floor=config.facade_floor,
                           module_rear=config.module_rear,
                           drawer_columns=config.drawer_columns, drawer_rows=config.drawer_rows,
                           **{**pattern_parameters(config), **wall_parameters(config)})
        generate = build
    print(f'Preparing {"multicolor label" if part == "label" else spec.name}', flush=True)
    with stage('cache_check'):
        expected = expected_for_spec(spec)
        destination, reasons = find_reusable(output, spec, expected, digest,
                                             git_provenance(PROJECT_ROOT))
        reused = destination is not None
        emit('cache_decision', part=part, reused=reused, reasons=reasons,
             dependency_digest=expected.get('digest'))
        print('Cache: ' + '; '.join(reasons), flush=True)
    if reused:
        print(f'Reusing checked build {destination.name}', flush=True)
    else:
        destination = generate(output, spec)
    emit('part_completed', part=part, build_id=destination.name, reused=reused)
    return destination.name


def _validate_set(config, builds, output, digest, receipt_id, *, strict_sources=False):
    from build123d import import_step
    from .assembly_validation import validate_assembly, validation_signature
    from ._build import verify_files
    from .generator import ASSEMBLY_PARTS
    from .build_cache import expected_for_spec, verify_dependency_record
    from .build import select_spec

    components, assembly_builds, component_dependencies = {}, [], {}
    with stage('assembly_import'):
        for kind, build_id in zip(config.parts, builds):
            directory = output / 'builds' / build_id
            if (Path(build_id).name != build_id or
                    not directory.resolve().is_relative_to((output / 'builds').resolve())):
                raise ValueError('Invalid component build ID')
            # The scheduler hands off immutable component IDs. Check every group,
            # including accessories, belongs to the job's pinned source.
            manifest = verify_files(directory)
            if 'dependencies' in manifest:
                spec = select_spec(kind, config.family, config.depth_units, config.height_units,
                    box_floor=config.box_floor, box_variant=config.box_variant,
                    box_rear_pattern=config.box_rear_pattern, facade_floor=config.facade_floor,
                    module_rear=config.module_rear, drawer_columns=config.drawer_columns,
                    drawer_rows=config.drawer_rows,
                    **{**pattern_parameters(config), **wall_parameters(config)})
                expected = expected_for_spec(spec)
                # A freshly generated dirty build is valid within this job's
                # pinned source; cross-source reuse additionally needs clean Git.
                ok, reasons = verify_dependency_record(directory, manifest, expected,
                    require_reusable=manifest.get('source_hash') != digest)
                if not ok:
                    raise RuntimeError('Component dependencies changed: ' + '; '.join(reasons))
                if manifest.get('source_hash') != digest:
                    from ._build import git_provenance
                    from .project import PROJECT_ROOT
                    current, built = git_provenance(PROJECT_ROOT), manifest.get('git') or {}
                    if (not current or not current.get('commit') or current.get('dirty') is not False
                            or not isinstance(built, dict) or not built.get('commit')
                            or built.get('dirty') is not False):
                        raise RuntimeError('Component reuse requires clean Git provenance.')
                component_dependencies[kind] = expected['digest']
            elif strict_sources:
                if manifest.get('source_hash') != digest:
                    raise RuntimeError('Component builds do not share the requested generator source.')
            if kind not in ASSEMBLY_PARTS:
                continue
            assembly_builds.append(build_id)
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
    with stage('assembly_validation'):
        validation = validate_assembly(config, components=components,
                                       progress=lambda message: print(message, flush=True))
        _check_source(digest, assembly=True)
        record = {'validation_signature': validation_signature(config),
                  'configuration': config.as_dict(), 'build_ids': assembly_builds,
                  'accessory_build_ids': [b for b in builds if b not in assembly_builds],
                  **({'component_dependencies': component_dependencies} if component_dependencies else {}),
                  'validation': validation}
        _write_receipt(output / 'web' / 'assemblies' / (receipt_id + '.json'), record)
        if not validation['passed']:
            failures = {key: [item for item in validation.get(key, []) if not item.get('passed')]
                        for key in ('solids', 'pairs', 'mating')}
            print(json.dumps({'assembly_fit_failures': failures}, indent=2), flush=True)
            raise RuntimeError('Assembly fit checks failed. Individual exports remain available; inspect the assembly warnings and validation report.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--task', help='One part group, or assembly after all groups have completed')
    parser.add_argument('--job-id', help='Parent queue job ID for the assembly receipt')
    parser.add_argument('--source-digest', help='Source revision pinned when this job started')
    parser.add_argument('--build-ids', help='JSON mapping part groups to checked build IDs')
    args = parser.parse_args(argv)
    config = parse_configuration(json.loads(args.configuration))
    if args.task is not None and args.task not in (*config.parts, 'assembly'):
        parser.error('Task is not a part of this configuration')
    if args.task == 'assembly' and config.part != 'set':
        parser.error('Assembly validation requires a complete set')
    if args.job_id is not None and (not args.job_id or Path(args.job_id).name != args.job_id
                                    or args.job_id in ('.', '..')):
        parser.error('Invalid job ID')
    with event_output(args.task is not None):
        try:
            from ._build import source_hashes, source_digest
            from .project import PROJECT_ROOT
            digest = source_digest(source_hashes(PROJECT_ROOT))
            if args.source_digest is not None and digest != args.source_digest:
                raise RuntimeError('Generator source changed since this job started. Generate again to use one revision.')
            if args.task == 'assembly':
                supplied = json.loads(args.build_ids or '{}')
                if (not isinstance(supplied, dict) or set(supplied) != set(config.parts)
                        or not all(isinstance(value, str) and value for value in supplied.values())):
                    raise ValueError('Assembly task requires exactly one checked build ID for every part group')
                builds = [supplied[part] for part in config.parts]
                _validate_set(config, builds, args.output, digest, args.job_id or args.receipt.stem,
                              strict_sources=True)
                _write_receipt(args.receipt, builds)
            else:
                builds = []
                for part in (config.parts if args.task is None else (args.task,)):
                    builds.append(_build_part(config, part, args.output, digest))
                    # A failed later part never hides earlier checked exports.
                    _write_receipt(args.receipt, builds)
                _check_source(digest)
                if args.task is None and config.part == 'set':
                    _validate_set(config, builds, args.output, digest, args.job_id or args.receipt.stem)
        except Exception as failure:
            emit('task_failed', error=f'{type(failure).__name__}: {failure}',
                 traceback=traceback.format_exc())
            raise
    print('All requested parts passed their export checks.', flush=True)


if __name__ == '__main__':
    main()
