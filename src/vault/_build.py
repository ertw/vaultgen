"""Load the dependency-free build package from the tooling repository in the local workspace."""
from pathlib import Path
import sys

source = Path(__file__).resolve().parents[4] / 'cad-tooling' / 'src'
if not (source / 'cad_build').is_dir():
    raise RuntimeError(f'Shared CAD build library is missing: {source}')
if str(source) not in sys.path:
    sys.path.insert(0, str(source))

from cad_build import (Build, run_build, source_hashes, source_digest, write_json,
                       verify_files, set_latest, git_provenance)
