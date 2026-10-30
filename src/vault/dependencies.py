"""Conservative file dependencies for checked CAD artifacts.

Imports in every branch and function are followed. This deliberately permits
false invalidations; it never treats one observed execution as a complete graph.
Non-Python inputs must be declared in ASSETS. Unknown local imports and dynamic
code loading make a fingerprint ineligible for reuse. This is input accounting,
not a sandbox or a proof that arbitrary Python cannot read undeclared inputs.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys

from .project import PROJECT_ROOT

SCHEMA = 'vault-dependencies/v1'
ROOTS = {
    'key': ('key_build',),
    'label': ('label_build',),
    'gridfinity_bins': ('bin_build',),
    'module': ('build',),
    'box': ('build',),
    'facade': ('build',),
    'rails': ('build',),
    'runner_guides': ('build',),
    'runner_slides': ('build',),
    **{part: ('accessories',) for part in
       ('spring', 'runner_stop', 'facade_cap', 'key_cap', 'latch')},
}
ASSETS = {
    'src/vault/label_config.py': ('src/vault/static/label-font.json',),
    'src/vault/native_renderer.py': ('src/vault/rasterizer.c',),
}
BUILD_INPUTS = ('pyproject.toml', 'uv.lock', 'flake.nix', 'flake.lock')
# These adapters are hashed in full. Following their generic dispatch imports
# would pull every part back into otherwise independent geometry branches.
LEAVES = {'src/vault/_build.py', 'src/vault/dependencies.py'}


def kind_for_parameters(parameters):
    """Recognize stored build parameters without importing geometry constructors."""
    if 'label_configuration' in parameters:
        return 'label'
    if 'gridfinity_configuration' in parameters:
        return 'gridfinity_bins'
    part = parameters.get('part', '')
    if not isinstance(part, str):
        return None
    if part == 'snap_key':
        return 'key'
    if part in ROOTS:
        return part
    for suffix, kind in (('_runner_guides', 'runner_guides'),
                         ('_runner_slides', 'runner_slides'),
                         ('_geared_rails', 'rails')):
        if part.endswith(suffix):
            return kind
    if part.endswith('_facade') or '_facade_floor_' in part:
        return 'facade'
    if '_box_' in part:
        return 'box'
    if '_module_' in part:
        return 'module'
    return None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def fingerprint_digest(record):
    """Recompute the digest of a stored fingerprint, excluding its digest field."""
    return _digest({key: value for key, value in record.items() if key != 'digest'})


def _normalized_parameters(value):
    """Treat equivalent JSON numbers consistently while preserving booleans."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalized_parameters(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalized_parameters(item) for item in value]
    return value


def dependency_graph(kind, *, root=PROJECT_ROOT):
    """Return the transitive local import graph, hashes, and reuse restrictions.

    The graph includes full files, package initializers, pinned environment
    definitions, explicit data assets, this policy, and shared build storage.
    """
    root = Path(root).resolve()
    hashes, edges, reasons, visited = {}, {}, [], set()
    if kind == 'rail':
        kind = 'rails'
    if kind not in ROOTS:
        return {'source_files': {}, 'edges': {}, 'reusable': False,
                'reasons': [f'Unknown dependency root: {kind}']}

    def read(relative, path=None):
        path = path or root / relative
        try:
            data = path.read_bytes()
        except OSError as error:
            reasons.append(f'Missing dependency {relative}: {error.strerror}')
            return None
        hashes[relative] = hashlib.sha256(data).hexdigest()
        edges.setdefault(relative, [])
        return data

    def resolve(module):
        location = 'src/' + module.replace('.', '/')
        for relative in (location + '.py', location + '/__init__.py'):
            if (root / relative).is_file():
                return relative
        return None

    def visit(relative):
        if relative in visited:
            return
        visited.add(relative)
        data = read(relative)
        if data is None or not relative.endswith('.py') or relative in LEAVES:
            return
        try:
            tree = ast.parse(data, filename=relative)
        except (SyntaxError, ValueError) as error:
            reasons.append(f'Cannot analyze {relative}: {error}')
            return
        module = relative.removeprefix('src/').removesuffix('.py').replace('/', '.')
        package = module.removesuffix('.__init__') if module.endswith('.__init__') else module.rpartition('.')[0]
        imports = set()
        dynamic_names = {'__import__', 'eval', 'exec'}
        dynamic_attributes = {'import_module', 'exec_module', 'load_module', 'spec_from_file_location',
                              'run_module', 'run_path'}
        # Collect aliases before examining calls. Breadth-first AST traversal
        # can encounter a call in one function before a loader import in another.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in {'importlib', 'builtins', 'runpy'}:
                for alias in node.names:
                    if alias.name in dynamic_attributes | {'__import__', 'eval', 'exec'}:
                        dynamic_names.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
                for alias in node.names:
                    if alias.name in {'importlib.import_module', 'builtins.__import__'}:
                        dynamic_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    components = package.split('.')
                    if node.level > len(components):
                        reasons.append(f'Unresolved relative import in {relative}:{node.lineno}')
                        continue
                    base = '.'.join(components[:len(components)-node.level+1])
                    imported = base + ('.' + node.module if node.module else '')
                else:
                    imported = node.module or ''
                imports.add(imported)
                # "from . import helper" imports a module; imported names may
                # also name child modules of a nonempty package.
                for alias in node.names:
                    if resolve(imported + '.' + alias.name):
                        imports.add(imported + '.' + alias.name)
                    elif (node.module is None or
                          (resolve(imported) or '').endswith('/__init__.py')):
                        # A package export could be provided by a dynamic
                        # __getattr__ or import hook. Require an explicit module
                        # rather than guessing whether it is a safe constant.
                        reasons.append(f'Unresolved package export {imported}.{alias.name} in {relative}')
            elif isinstance(node, ast.Call):
                function = node.func
                if ((isinstance(function, ast.Name) and function.id in dynamic_names)
                        or (isinstance(function, ast.Attribute) and function.attr in dynamic_attributes)):
                    reasons.append(f'Dynamic code loading in {relative}:{node.lineno}')
        targets = set(ASSETS.get(relative, ()))
        # Importing a submodule executes each package initializer too.
        for imported in imports:
            top = imported.split('.')[0]
            if (top == 'vault' or (root / 'src' / (top + '.py')).is_file()
                    or (root / 'src' / top).is_dir()):
                target = resolve(imported)
                if target is None:
                    reasons.append(f'Unresolved local import {imported} in {relative}')
                    continue
                targets.add(target)
                segments = imported.split('.')
                for index in range(1, len(segments)):
                    initializer = 'src/' + '/'.join(segments[:index]) + '/__init__.py'
                    if (root / initializer).is_file():
                        targets.add(initializer)
        edges[relative] = sorted(targets)
        for target in sorted(targets):
            visit(target)

    for name in ROOTS[kind]:
        visit('src/vault/' + name + '.py')
    for relative in ('src/vault/__init__.py', 'src/vault/dependencies.py', *BUILD_INPUTS):
        visit(relative)
    tooling = root.parents[1] / 'cad-tooling' / 'src' / 'cad_build'
    shared = sorted(tooling.glob('*.py'))
    if not shared:
        reasons.append('Shared cad_build sources unavailable')
    for path in shared:
        read('_build_system/' + path.name, path)
    if 'src/vault/_build.py' in edges:
        edges['src/vault/_build.py'] = sorted('_build_system/' + p.name for p in shared)
    return {'source_files': dict(sorted(hashes.items())), 'edges': dict(sorted(edges.items())),
            'reusable': not reasons, 'reasons': sorted(set(reasons))}


def toolchain_identity():
    """Identify the actual interpreter, installed packages, native renderer and environment.

    Lockfiles alone cannot establish which environment is executing a build.
    Versions identify installed distributions, not every byte of third-party code;
    builds still rely on the managed/pinned environment described in the docs.
    """
    packages = sorted((dist.metadata.get('Name', ''), dist.version)
                      for dist in importlib.metadata.distributions())
    environment = {key: os.environ.get(key) for key in
                   ('CC', 'PATH', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'PYTHONPATH',
                    'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                    'CPATH', 'LIBRARY_PATH', 'NIX_CFLAGS_COMPILE', 'NIX_LDFLAGS')}
    compiler, compiler_error = None, None
    try:
        command = shlex.split(os.environ.get('CC', ''))
        if not command:
            command = next(([path] for name in ('cc', 'gcc', 'clang')
                            if (path := shutil.which(name))), [])
        if not command:
            candidates = sorted(Path('/nix/store').glob('*gcc-wrapper*/bin/gcc'))
            command = [str(candidates[-1])] if candidates else []
        if command:
            executable = shutil.which(command[0])
            if not executable:
                raise OSError(f'Compiler unavailable: {command[0]}')
            executable = Path(executable).resolve()
            version = subprocess.run([*command, '--version'], check=True, capture_output=True,
                                     timeout=5).stdout.decode(errors='replace')
            compiler = {'command': command, 'executable': str(executable), 'version': version,
                        'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest()}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        compiler_error = str(error)
    return {'python': sys.version, 'implementation': sys.implementation.name,
            'cache_tag': sys.implementation.cache_tag, 'executable': sys.executable,
            'executable_sha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            'platform': platform.platform(), 'machine': platform.machine(),
            'packages': packages, 'environment': environment,
            'compiler': compiler, 'compiler_error': compiler_error}


def fingerprint(kind, parameters, *, root=PROJECT_ROOT, toolchain=None):
    """Hash the complete declared inputs to one checked part build."""
    graph = dependency_graph(kind, root=root)
    identity = toolchain_identity() if toolchain is None else toolchain
    reasons = list(graph['reasons'])
    if identity.get('compiler_error'):
        reasons.append('Compiler identity unavailable: ' + identity['compiler_error'])
    record = {'schema': SCHEMA, 'kind': 'rails' if kind == 'rail' else kind,
              'parameters': _normalized_parameters(parameters), **graph, 'toolchain': identity,
              'reusable': not reasons, 'reasons': reasons}
    # Normalize tuples and numeric JSON containers so round-tripped manifests
    # compare exactly with newly computed fingerprints.
    record = json.loads(json.dumps(record, sort_keys=True, allow_nan=False))
    return {**record, 'digest': _digest(record)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=sorted(ROOTS), default='key')
    parser.add_argument('--parameters', type=Path, help='Resolved parameters JSON')
    parser.add_argument('--compare', type=Path, help='Build manifest or saved fingerprint JSON')
    args = parser.parse_args(argv)
    parameters = json.loads(args.parameters.read_text()) if args.parameters else {}
    record = fingerprint(args.kind, parameters)
    if args.compare:
        previous = json.loads(args.compare.read_text())
        previous = previous.get('dependencies', previous)
        old, current = previous.get('source_files', {}), record['source_files']
        record['changes'] = {path: ('added' if path not in old else 'removed' if path not in current else
                                    'unchanged' if old[path] == current[path] else 'changed')
                             for path in sorted(old.keys() | current.keys())}
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
