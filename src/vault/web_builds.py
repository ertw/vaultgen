"""Read immutable builds, resolve assembly previews, and package checked downloads."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

from .generator import Configuration
from .project import PROJECT_ROOT
from ._build import git_provenance


def freshness(manifest, current):
    built = manifest.get("git") or {}
    reasons = []
    if current is None:
        reasons.append("Repository revision unavailable; rebuild to verify this cached part.")
    else:
        if current.get("dirty"):
            reasons.append("Repository has uncommitted changes; rebuild to include current code.")
        if not built.get("commit"):
            reasons.append("Cached build revision is unknown; rebuild recommended.")
        elif built["commit"] != current["commit"]:
            reasons.append("Cached build is from a different commit; rebuild for the current revision.")
    if built.get("dirty"):
        reasons.append("Cached build was generated with uncommitted changes.")
    return {"warning": bool(reasons), "reasons": reasons, "commit": built.get("commit")}


BUILD_ID = re.compile(r'\d{8}T\d{12}Z-[a-f0-9]{12}')
PUBLIC_SUFFIXES = {'.stl', '.step', '.png', '.3mf', '.txt'}


class BuildFiles:
    """Serve only validated, immutable artifacts and their recorded metadata."""

    def __init__(self, output):
        self.root = Path(output).resolve() / 'builds'

    def read(self, build_id):
        if not BUILD_ID.fullmatch(build_id):
            raise FileNotFoundError('Unknown build')
        path = self.root / build_id
        if path.resolve().parent != self.root:
            raise FileNotFoundError('Unknown build')
        file = path / 'manifest.json'
        if not file.resolve().is_relative_to(path):
            raise FileNotFoundError('Unknown build')
        manifest = json.loads(file.read_text())
        if manifest.get('passed') is not True or manifest.get('build_id') != build_id:
            raise FileNotFoundError('Build has not passed validation')
        return path, manifest

    def artifact(self, build_id, relative):
        path, manifest = self.read(build_id)
        file = path / relative
        if (not relative or relative.startswith('/') or '..' in Path(relative).parts
                or relative.startswith('source/') or file.suffix not in PUBLIC_SUFFIXES
                or not file.resolve().is_relative_to(path)
                or relative not in manifest['checksums']):
            raise FileNotFoundError('Unknown artifact')
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest['checksums'][relative]:
            raise ValueError('Artifact checksum failed; generate a fresh build')
        return data

    def assembly(self, configuration):
        """Resolve one immutable build per group; never infer legacy mesh poses."""
        from .assembly import assembly_definition
        from .generator import ACCESSORY_PARTS, ASSEMBLY_PARTS
        from .assembly_validation import validation_signature
        definition = assembly_definition(configuration)
        repository = git_provenance(PROJECT_ROOT)
        builds = self.history(repository)
        from .spec import PATTERN_FIELDS
        module_pattern_fields = PATTERN_FIELDS if configuration.wall_pattern != 'plain' else ('wall_pattern',)
        keys = {'module': ('family', 'depth_units', 'height_units', 'module_rear', 'drawer_columns', *module_pattern_fields),
                'box': ('family', 'depth_units', 'height_units', 'box_floor', 'box_variant', 'box_rear_pattern'),
                'facade': ('family', 'height_units', 'facade_floor'), 'rails': ('family',),
                'runner_guides': ('depth_units',), 'runner_slides': ('depth_units',),
                **{kind: () for kind in ACCESSORY_PARTS}}
        defaults, selected = Configuration().as_dict(), configuration.as_dict()
        selected_drawer = {**selected, 'family': configuration.drawer_family,
                           'height_units': configuration.drawer_height_units}
        matched = {kind: next((build for build in builds if build['kind'] == kind
                    and not build['legacy_partitioned_module'] and
                    all(build['configuration'].get(key, defaults[key]) ==
                        (selected if kind == 'module' else selected_drawer)[key]
                        for key in fields)), None) for kind, fields in keys.items()}
        instances, missing, warnings = [], [], []
        used = {}
        for item in definition['instances']:
            build = matched[item['kind']]
            part = next((part for part in build['parts']
                         if part.get('assembly_mesh', {}).get('component') == item['component']), None) if build else None
            if not part or not part.get('assembly_url'):
                missing.append({'id': item['id'], 'kind': item['kind'], 'label': item['label'],
                                'reason': ('Rebuild this part to generate its finished assembly mesh.' if build
                                           else 'Not generated yet for this configuration.')})
                continue
            used[build['id']] = build
            instances.append({**item, 'mesh_url': part['assembly_url'],
                              'build_id': build['id'], 'freshness': build['freshness']})
        for build in used.values():
            warnings.extend(build['freshness']['reasons'])
        if len({build.get('source_hash') for build in used.values()}) > 1:
            warnings.append('These cached components were generated from different source revisions.')
        # A checked receipt certifies these exact immutable component builds.
        validation = None
        checked_builds = {build_id for build_id, build in used.items() if build['kind'] in ASSEMBLY_PARTS}
        accessory_builds = set(used) - checked_builds
        signature = validation_signature(configuration)
        receipt_root = self.root.parent / 'web' / 'assemblies'
        for path in sorted(receipt_root.glob('*.json'), key=lambda path: path.stat().st_mtime_ns, reverse=True):
            try:
                receipt = json.loads(path.read_text())
                if (receipt.get('validation_signature') == signature and
                        receipt['configuration'] == selected and
                        set(receipt['build_ids']) == checked_builds and
                        set(receipt.get('accessory_build_ids', [])) == accessory_builds and not missing):
                    validation = receipt['validation']
                    break
            except (OSError, ValueError, KeyError):
                continue
        if validation and not validation.get('passed'):
            failures = [item for key in ('pairs', 'mating', 'solids')
                        for item in validation.get(key, []) if not item.get('passed')]
            labels = [' / '.join(item.get('instances', [])) or item.get('instance', 'geometry')
                      for item in failures]
            labels.extend(validation.get('definition_errors', []))
            warnings.append('Assembly fit check failed: ' + ', '.join(dict.fromkeys(labels)) + '. See the build log for details.')
        elif not validation:
            warnings.append('This combination of cached parts has no passing assembly fit check. Generate a complete set to check it.')
        columns = '²' if configuration.drawer_columns == 2 else ''
        rows = ' · 4 drawers' if configuration.drawer_rows == 2 else ''
        from .spec import WALL_PATTERNS
        pattern = f' · {WALL_PATTERNS[configuration.wall_pattern]}' if configuration.wall_pattern != 'plain' else ''
        if pattern and configuration.pattern_construction == 'corrugated':
            pattern += ' corrugated'
        if configuration.box_variant == 'gridfinity':
            pattern += ' · Floorless Gridfinity' if configuration.box_floor == 0 else ' · Gridfinity'
        if configuration.box_rear_pattern != 'plain':
            pattern += f' · {WALL_PATTERNS[configuration.box_rear_pattern]} corrugated box rear'
        if configuration.facade_floor == 0.8:
            pattern += ' · 0.8 mm facade floor'
        return {**definition, 'name': f'{configuration.family}{configuration.depth_units}{columns} · {configuration.height_units}F{rows}{pattern} complete set',
                'instances': instances, 'missing': missing, 'warnings': list(dict.fromkeys(warnings)),
                'complete': not missing, 'repository': repository, 'validation': validation}

    def describe(self, build_id, repository=None):
        path, manifest = self.read(build_id)
        parameters = json.loads((path / 'resolved-parameters.json').read_text())
        part = parameters.get('part', '')
        from .generator import ACCESSORY_PARTS
        kind = ('key' if part == 'snap_key' else
                part if part in ACCESSORY_PARTS else
                'label' if part.endswith('_label') else
                'gridfinity_bins' if 'gridfinity_configuration' in parameters else
                'runner_guides' if part.endswith('_runner_guides') else
                'runner_slides' if part.endswith('_runner_slides') else
                'rails' if part.endswith('_geared_rails') else
                'facade' if part.endswith('_facade') or '_facade_floor_' in part else
                'box' if '_box_' in part else 'module')
        config = {key: parameters[key] for key in ('family', 'depth_units', 'height_units')
                  if key in parameters}
        config['part'] = kind
        if kind == 'label':
            config = parameters['label_configuration']
        if kind == 'gridfinity_bins':
            config = parameters['gridfinity_configuration']
        if kind == 'box':
            config['box_floor'] = parameters.get('box_floor', 0.8)
            config['box_variant'] = parameters.get('box_variant', 'plain')
            config['box_rear_pattern'] = parameters.get('box_rear_pattern', 'plain')
        if kind == 'facade':
            config['facade_floor'] = parameters.get('facade_floor', 'default')
        if kind == 'module':
            from .spec import PATTERN_DEFAULTS
            config['module_rear'] = parameters.get('module_rear', 0.9)
            config['drawer_columns'] = parameters.get('drawer_columns', 1)
            config['drawer_rows'] = parameters.get('drawer_rows', 1)
            config.update({key: parameters.get(key, value) for key, value in PATTERN_DEFAULTS.items()})
        def url(relative):
            return f'/files/{build_id}/{relative}' if relative in manifest['checksums'] else None
        parts = []
        for name, details in manifest.get('parts', {}).items():
            assembly = details.get('assembly_mesh') or {}
            assembly_ok = (assembly.get('schema') == 'vault-assembly-mesh/v1'
                           and assembly.get('coordinates') == 'native' and assembly.get('finished') is True)
            parts.append({'assembly_mesh': assembly if assembly_ok else {},
                          'assembly_url': url(assembly.get('path')) if assembly_ok else None,
                          'name': name, 'print_bbox_mm': details.get('print_bbox_mm', []),
                          'print_note': details.get('print_note', ''),
                          'color': details.get('color'), 'role': details.get('role'),
                          'stl_url': url(f'stl/{name}.stl'),
                          'step_url': url(f'{name}_print.step'),
                          'print_step_url': url(f'{name}_print.step')})
        return {'freshness': freshness(manifest, repository if repository is not None else git_provenance(PROJECT_ROOT)),
                'source_hash': manifest.get('source_hash'),
                'legacy_partitioned_module': kind == 'module' and '_2_rows_module_' in part,
                'id': build_id, 'name': manifest.get('name', part), 'kind': kind,
                'configuration': config, 'parts': parts, 'step_url': url(f'{part}.step'),
                'label_dimensions': manifest.get('label_dimensions') if kind == 'label' else None,
                'gridfinity_layout': manifest.get('gridfinity_layout') if kind == 'gridfinity_bins' else None,
                'design_metrics': manifest.get('design_metrics') if kind == 'gridfinity_bins' else None,
                'three_mf_url': url(manifest.get('multicolor_3mf')),
                'bundle_url': f'/api/builds/{build_id}/bundle.zip',
                'instructions_url': url(manifest.get('print_instructions')),
                'preview_url': url('review/isometric.png'),
                'created_at': datetime.strptime(build_id[:22], '%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc).isoformat()}

    def history(self, repository=None):
        result = []
        repository = repository if repository is not None else git_provenance(PROJECT_ROOT)
        for path in sorted(self.root.glob('*'), reverse=True):
            try:
                item = self.describe(path.name, repository)
                config = item['configuration']
                if (config['part'] in ('label', 'gridfinity_bins', 'key', 'spring', 'runner_stop', 'facade_cap', 'key_cap', 'latch') or ((config.get('family') in ('S', 'M', 'L')
                     or (config['part'] in ('runner_guides', 'runner_slides') and 'family' not in config))
                        and config.get('height_units', 1) in (1, 2)
                        and config.get('depth_units', 4) in range(3, 8)
                        and (config.get('drawer_columns', 1) == 1 or
                             (config.get('drawer_columns') == 2 and config.get('family') == 'L'))
                        and (config.get('drawer_rows', 1) == 1 or
                             (config.get('drawer_rows') == 2 and config.get('drawer_columns') == 2
                              and config.get('family') == 'L' and config.get('height_units') == 2)))):
                    result.append(item)
            except (OSError, ValueError, KeyError):
                continue
        return result

    def write_bundle(self, archive, builds, configuration):
        """Write a print ZIP, verifying every included immutable artifact."""
        print_plan = None
        if configuration.get('part') not in ('label', 'gridfinity_bins'):
            try:
                config = Configuration.parse(configuration)
                print_plan = {'schema': 'vault-print-plan/v1', 'configuration': config.as_dict(),
                              'files': []}
            except ValueError:
                # Keep older, broader research builds downloadable.
                pass
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('configuration.json', json.dumps(configuration, indent=2))
            for build in builds:
                _, manifest = self.read(build['id'])
                for relative in manifest['checksums']:
                    if relative.startswith(('source/', 'preview/')) or Path(relative).suffix not in {'.stl', '.step', '.3mf', '.txt'}:
                        continue
                    bundle.writestr(f'{build["kind"]}/{relative}', self.artifact(build['id'], relative))
                    if print_plan is not None and Path(relative).suffix == '.stl':
                        print_plan['files'].append({'path': f'{build["kind"]}/{relative}',
                            'kind': build['kind'], 'build_id': build['id'],
                            'copies': config.print_copies[build['kind']],
                            'optional': build['kind'] == 'key_cap'})
            bundle.writestr('parts.json', json.dumps(builds, indent=2))
            if print_plan is not None:
                bundle.writestr('print-plan.json', json.dumps(print_plan, indent=2))
                instructions = [
                    'Print quantities for the configuration in configuration.json.',
                    'Each file is included once; print the number of copies listed below.',
                    'Use the supplied print orientation and each part\'s print notes in parts.json.',
                    'Remove sacrificial supports before assembly. CAD checks do not establish printed fit.',
                    '',
                ]
                instructions.extend(f'{item["copies"]} × {item["path"]}' +
                                    (' (optional)' if item['optional'] else '')
                                    for item in print_plan['files'])
                bundle.writestr('PRINTING.txt', '\n'.join(instructions) + '\n')
