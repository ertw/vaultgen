"""Load the dependency-free build package from the tooling repository in the local workspace."""
from pathlib import Path
import sys

source = Path(__file__).resolve().parents[4] / 'cad-tooling' / 'src'
if not (source / 'cad_build').is_dir():
    raise RuntimeError(f'Shared CAD build library is missing: {source}')
if str(source) not in sys.path:
    sys.path.insert(0, str(source))

from cad_build import (Build, run_build as _run_build, source_hashes, source_digest, write_json,
                       verify_files, set_latest, git_provenance)


def run_build(root, configuration_hash, generate, *, parameters, **kwargs):
    """Retain full provenance and record the narrower artifact dependency graph.

    The shared transaction still checks the complete source snapshot. Checking
    the graph again also guards runtime/asset inputs outside that snapshot.
    """
    from .dependencies import fingerprint, kind_for_parameters

    kind = kind_for_parameters(parameters)
    dependencies = fingerprint(kind, parameters, root=root)

    def checked_generate(state):
        metadata, viewer = generate(state)
        if fingerprint(kind, parameters, root=root) != dependencies:
            raise RuntimeError('Build dependencies or toolchain changed during generation. Generate again.')
        write_json(state.stage / 'dependencies.json', dependencies)
        return {**metadata, 'dependencies': dependencies}, viewer

    return _run_build(root, configuration_hash, checked_generate,
                      parameters=parameters, **kwargs)
