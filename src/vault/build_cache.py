"""Reuse immutable artifacts only when their declared inputs still agree."""
import json
from pathlib import Path


def expected_for_spec(spec):
    from dataclasses import is_dataclass
    from .build import build_parameters
    from .dependencies import fingerprint, kind_for_parameters
    if not is_dataclass(spec):
        return fingerprint(None, {'part': spec.slug})
    parameters = build_parameters(spec)
    return fingerprint(kind_for_parameters(parameters), parameters)


def compatible(manifest, expected, *, require_reusable=True):
    """Explain input differences independently of the build's Git provenance."""
    from .dependencies import fingerprint_digest
    built = manifest.get('dependencies')
    if not isinstance(built, dict) or not isinstance(expected, dict):
        return False, ['Dependency metadata unavailable.']
    if (not isinstance(built.get('source_files'), dict)
            or not isinstance(built.get('parameters'), dict)
            or not isinstance(built.get('edges'), dict)
            or not isinstance(built.get('toolchain'), dict)):
        return False, ['Dependency metadata is malformed.']
    reasons = []
    if require_reusable and (built.get('reusable') is not True or expected.get('reusable') is not True):
        reasons.extend(expected.get('reasons') or built.get('reasons') or ['Dependencies are uncertain.'])
    if built.get('schema') != expected.get('schema'):
        reasons.append('Dependency schema changed.')
    if built.get('kind') != expected.get('kind') or built.get('parameters') != expected.get('parameters'):
        reasons.append('Resolved build parameters changed.')
    before, after = built.get('source_files', {}), expected.get('source_files', {})
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    if changed:
        reasons.append('Dependency files changed: ' + ', '.join(changed))
    if built.get('toolchain') != expected.get('toolchain'):
        reasons.append('Build toolchain changed.')
    if built.get('edges') != expected.get('edges'):
        reasons.append('Dependency graph changed.')
    if built.get('digest') != fingerprint_digest(built) or built.get('digest') != expected.get('digest'):
        if not reasons:
            reasons.append('Dependency fingerprint changed or is invalid.')
    return not reasons, reasons


def verify_dependency_record(directory, manifest, expected, *, require_reusable=True):
    """Metadata must agree with its checksummed, immutable source documents."""
    ok, reasons = compatible(manifest, expected, require_reusable=require_reusable)
    if not ok:
        return False, reasons
    for name, value in (('dependencies.json', manifest['dependencies']),
                        ('resolved-parameters.json', expected['parameters'])):
        if (name not in manifest.get('checksums', {}) or
                json.loads((directory / name).read_text()) != value):
            return False, [f'Checked {name} is missing or inconsistent.']
    return True, []


def find_reusable(output, spec, expected, digest, current):
    """Search checked history, retaining the strict legacy latest-pointer path."""
    from ._build import verify_files
    output = Path(output).resolve()
    if not current or not current.get('commit'):
        return None, ['Repository revision unavailable.']
    if current.get('dirty') is not False:
        return None, ['Repository has uncommitted changes.']
    latest = output / 'latest' / spec.slug
    candidates = [latest] if latest.is_dir() else []
    candidates.extend(sorted((output / 'builds').glob('*'), reverse=True))
    seen, reasons = set(), ['No matching checked build.']
    for candidate in candidates:
        directory = candidate.resolve()
        if directory in seen or directory.parent != output / 'builds':
            continue
        seen.add(directory)
        try:
            # Read cheap metadata before hashing potentially large history files.
            manifest = json.loads((directory / 'manifest.json').read_text())
            if not isinstance(manifest, dict):
                if candidate == latest:
                    reasons = ['Cached build manifest is malformed.']
                continue
            if 'dependencies' in manifest:
                ok, why = compatible(manifest, expected)
                if not ok:
                    if candidate == latest:
                        reasons = why
                    continue
                built_git = manifest.get('git') or {}
                if (not isinstance(built_git, dict) or not built_git.get('commit')
                        or built_git.get('dirty') is not False):
                    if candidate == latest:
                        reasons = ['Cached build has dirty or unknown Git provenance.']
                    continue
                if manifest.get('build_id') != directory.name:
                    continue
                manifest = verify_files(directory)
                ok, why = verify_dependency_record(directory, manifest, expected)
                if ok:
                    return directory, ['Matching dependency fingerprint and checked artifacts.']
                reasons = why
            elif candidate == latest:
                # Old records have no dependency proof. Their original policy
                # remains in force; never infer compatibility across revisions.
                manifest = verify_files(directory)
                if manifest.get('source_hash') == digest and manifest.get('git') == current:
                    return directory, ['Matching legacy source digest and clean Git revision.']
                reasons = ['Legacy build source digest or Git revision changed.']
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            if candidate == latest:
                reasons = [f'Cached build verification failed: {error}']
    return None, reasons
