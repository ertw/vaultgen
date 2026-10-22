"""Optional local C rasterizer, compiled on demand without downloaded packages."""
from __future__ import annotations

import ctypes
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile

import numpy as np


def _compiler():
    configured = shlex.split(os.environ.get('CC', ''))
    if configured:
        return configured
    for name in ('cc', 'gcc', 'clang'):
        if executable := shutil.which(name):
            return [executable]
    # The project normally gets cc from nix develop. Also accept an installed
    # Nix compiler when using the cached local runtime outside that shell.
    candidates = sorted(Path('/nix/store').glob('*gcc-wrapper*/bin/gcc'))
    return [str(candidates[-1])] if candidates else None


@lru_cache(maxsize=1)
def native_rasterizer():
    """Return (ctypes function, None), or (None, reason) for Python fallback."""
    try:
        compiler = _compiler()
        if compiler is None:
            return None, 'no C compiler found'
        source = Path(__file__).with_name('rasterizer.c')
        flags = ['-O3', '-std=c99', '-ffp-contract=off', '-fPIC']
        flags += ['-dynamiclib'] if sys.platform == 'darwin' else ['-shared']
        identity = source.read_bytes() + repr((compiler, flags, sys.platform, platform.machine())).encode()
        digest = hashlib.sha256(identity).hexdigest()[:20]
        cache = source.parents[2] / '.cache' / 'renderer'
        cache.mkdir(parents=True, exist_ok=True)
        suffix = '.dylib' if sys.platform == 'darwin' else '.so'
        library = cache / f'rasterizer-{digest}{suffix}'
        if not library.exists():
            # Compile to a unique path so parallel processes never load a
            # half-written shared library or overwrite each other's output.
            with tempfile.TemporaryDirectory(prefix='compile-', dir=cache) as temporary:
                candidate = Path(temporary) / f'rasterizer{suffix}'
                subprocess.run(
                    [*compiler, *flags, str(source), '-o', str(candidate), '-lm'],
                    check=True, capture_output=True, timeout=60,
                )
                os.replace(candidate, library)
        loaded = ctypes.CDLL(str(library))
        rasterizer = loaded.vault_rasterize
        contiguous = np.ctypeslib.ndpointer
        rasterizer.argtypes = [
            contiguous(dtype=np.float64, ndim=2, flags='C_CONTIGUOUS'),
            contiguous(dtype=np.float64, ndim=1, flags='C_CONTIGUOUS'),
            contiguous(dtype=np.int64, ndim=2, flags='C_CONTIGUOUS'),
            contiguous(dtype=np.int64, ndim=1, flags='C_CONTIGUOUS'),
            contiguous(dtype=np.uint8, ndim=2, flags='C_CONTIGUOUS'),
            ctypes.c_size_t, ctypes.c_int, ctypes.c_int,
            contiguous(dtype=np.uint8, ndim=3, flags='C_CONTIGUOUS'),
            contiguous(dtype=np.float64, ndim=2, flags='C_CONTIGUOUS'),
        ]
        rasterizer.restype = None
        return rasterizer, None
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError) as error:
        return None, str(error)
