"""Worker fit receipts certify exact checked STEP builds and preserve failures."""
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from vault import build as build_api, assembly_validation
from vault.generator import Configuration, ASSEMBLY_PARTS
from vault.spec import PATTERN_DEFAULTS
from vault.web_worker import main


class AssemblyWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.receipt = self.output / 'requested-set.receipt'
        self.configuration = Configuration('L', 6, 2, 'set', 3., 2.)
        self.build_ids = []
        self.expected_steps = {}
        self.untrusted_metadata = False
        self.corrupt_step = False

    def build(self, output, spec):
        self.assertEqual(output, self.output)
        build_id = f'20261024T010000{len(self.build_ids):06d}Z-0123456789ab'
        self.build_ids.append(build_id)
        directory = output / 'builds' / build_id
        roles = {'rails': ('plain', 'retained'), 'runner_guides': ('left', 'right'),
                 'runner_slides': ('left', 'right')}.get(spec.kind, ('single',))
        parts, checksums = {}, {}
        for role in roles:
            relative = f'preview/assembly/{role}.step'
            finished = directory / relative
            finished.parent.mkdir(parents=True, exist_ok=True)
            finished.write_bytes(f'finished-native-{spec.kind}-{role}'.encode())
            checksums[relative] = hashlib.sha256(finished.read_bytes()).hexdigest()
            # A checked printable STEP is deliberately present as a decoy.
            # The worker must validate the finished asset referenced in metadata.
            printable = directory / f'{role}_print.step'
            printable.write_bytes(b'print orientation with sacrificial supports')
            checksums[printable.name] = hashlib.sha256(printable.read_bytes()).hexdigest()
            metadata = {'schema': 'vault-assembly-mesh/v1', 'finished': True,
                        'coordinates': 'native', 'component': role, 'step_path': relative}
            if self.untrusted_metadata and spec.kind == 'module':
                metadata['finished'] = False
            parts[role] = {'assembly_mesh': metadata}
            self.expected_steps[spec.kind, role] = finished
        (directory / 'manifest.json').write_text(json.dumps({
            'passed': True, 'build_id': build_id, 'parts': parts, 'checksums': checksums,
        }))
        if self.corrupt_step and spec.kind == 'runner_slides':
            finished.write_bytes(b'changed after the build passed')
        return directory

    def run_worker(self, passed=True):
        self.report = {'passed': passed, 'configuration': self.configuration.as_dict(),
                       'pairs': [{'instances': ['module', 'box'], 'passed': passed}]}
        self.import_step = Mock(side_effect=lambda path: ('imported-native-step', Path(path)))

        def validate(configuration, *, components, progress=None):
            self.assertEqual(configuration, self.configuration)
            self.assertEqual(json.loads(self.receipt.read_text()), self.build_ids)
            self.assertEqual(components, {
                key: ('imported-native-step', path) for key, path in self.expected_steps.items() if key[0] in ASSEMBLY_PARTS})
            return self.report

        self.validate = Mock(side_effect=validate)
        self.select_spec = Mock(side_effect=lambda kind, *args, **kwargs:
                                SimpleNamespace(kind=kind, slug=f'fixture_{kind}', name=kind))
        argv = ['vault.web_worker', '--configuration', json.dumps(self.configuration.as_dict()),
                '--output', str(self.output), '--receipt', str(self.receipt)]
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', argv))
            stack.enter_context(patch.dict(sys.modules, {'build123d': SimpleNamespace(import_step=self.import_step)}))
            stack.enter_context(patch.object(build_api, 'select_spec', self.select_spec))
            stack.enter_context(patch.object(build_api, 'build', side_effect=self.build))
            stack.enter_context(patch('vault._build.source_hashes', return_value={'source.py': 'stable-source'}))
            stack.enter_context(patch.object(assembly_validation, 'validate_assembly', self.validate))
            stack.enter_context(redirect_stdout(io.StringIO()))
            main()

    def read_assembly_receipt(self):
        destination = self.output / 'web' / 'assemblies'
        self.assertEqual([path.name for path in destination.iterdir()], ['requested-set.json'])
        return json.loads((destination / 'requested-set.json').read_text())

    def test_success_checks_exact_native_builds_and_publishes_signature(self):
        from vault.assembly_validation import validation_signature
        self.run_worker()
        self.assertEqual(json.loads(self.receipt.read_text()), self.build_ids)
        self.assertEqual(len(self.build_ids), 12)
        self.assertEqual(self.import_step.call_count, 9)
        self.validate.assert_called_once()
        self.assertEqual(self.read_assembly_receipt(), {
            'configuration': self.configuration.as_dict(), 'build_ids': self.build_ids[:6], 'accessory_build_ids': self.build_ids[6:],
            'validation': self.report, 'validation_signature': validation_signature(self.configuration),
        })
        for call in self.select_spec.call_args_list:
            self.assertEqual(call.args[1:], ('L', 6, 2))
            self.assertEqual(call.kwargs, {'wall_perimeters': None, 'nozzle_size': .6, 'box_floor': 3., 'box_variant': 'plain', 'box_rear_pattern': 'plain', 'module_rear': 2.,
                                          'facade_floor': 'default',
                                          'drawer_columns': 1, 'drawer_rows': 1, **PATTERN_DEFAULTS})

    def assert_configuration_preserved(self, configuration):
        self.configuration = configuration
        self.run_worker()
        values = configuration.as_dict()
        axes = tuple(values.pop(key) for key in ('family', 'depth_units', 'height_units'))
        values.pop('part')
        for call in self.select_spec.call_args_list:
            self.assertEqual(call.args[1:], axes)
            self.assertEqual(call.kwargs, values)
        self.assertEqual(self.read_assembly_receipt()['configuration'], configuration.as_dict())
        self.assertEqual(len(self.build_ids), 12)

    def test_pattern_settings_are_preserved_in_selection_and_fit_receipt(self):
        self.assert_configuration_preserved(Configuration(
            wall_pattern='miura', pattern_pitch=20, pattern_depth=1.4, pattern_line_width=.8,
            pattern_faces='sides', pattern_construction='corrugated'))

    def test_shared_walls_preserve_nozzle_count_and_pattern_in_worker_and_receipt(self):
        self.assert_configuration_preserved(Configuration.parse_request(dict(
            wall_pattern='miura', wall_perimeters=1, nozzle_size=.8, pattern_pitch=20)))

    def test_gridfinity_variant_is_preserved_in_selection_and_fit_receipt(self):
        self.assert_configuration_preserved(Configuration(box_variant='gridfinity'))

    def test_facade_floor_is_preserved_in_selection_and_fit_receipt(self):
        self.assert_configuration_preserved(Configuration(facade_floor=.8))

    def test_floorless_gridfinity_is_preserved_in_selection_and_fit_receipt(self):
        self.assert_configuration_preserved(Configuration(
            box_variant='gridfinity', box_floor=0, box_rear_pattern='miura'))

    def test_box_rear_and_module_patterns_remain_independent_in_worker(self):
        self.assert_configuration_preserved(Configuration(
            box_variant='gridfinity', box_rear_pattern='waffle', wall_pattern='miura',
            pattern_pitch=20, pattern_depth=1.4, pattern_line_width=.8,
            pattern_construction='corrugated'))

    def test_double_drawer_layout_is_preserved_in_selection_and_fit_receipt(self):
        self.assert_configuration_preserved(Configuration('L', 6, 2, 'set', 3., 2., drawer_columns=2))

    def test_four_drawer_layout_is_preserved_in_selection_and_fit_receipt(self):
        self.assert_configuration_preserved(Configuration(
            'L', 6, 2, 'set', 3., 2., drawer_columns=2, drawer_rows=2))

    def test_failed_fit_publishes_failed_audit_and_preserves_all_build_receipts(self):
        with self.assertRaisesRegex(RuntimeError, 'Assembly fit checks failed'):
            self.run_worker(passed=False)
        self.assertEqual(json.loads(self.receipt.read_text()), self.build_ids)
        self.assertEqual(len(self.build_ids), 12)
        record = self.read_assembly_receipt()
        self.assertEqual(record['build_ids'], self.build_ids[:6])
        self.assertEqual(record['validation'], self.report)
        self.assertFalse(record['validation']['passed'])

    def test_printable_metadata_cannot_be_certified_as_finished_geometry(self):
        self.untrusted_metadata = True
        with self.assertRaisesRegex(RuntimeError, 'finished assembly geometry'):
            self.run_worker()
        self.import_step.assert_not_called()
        self.validate.assert_not_called()
        self.assertEqual(json.loads(self.receipt.read_text()), self.build_ids)
        self.assertFalse((self.output / 'web' / 'assemblies').exists())

    def test_changed_finished_step_fails_checksum_before_fit_is_certified(self):
        self.corrupt_step = True
        with self.assertRaisesRegex(RuntimeError, 'Artifact checksum failed'):
            self.run_worker()
        self.validate.assert_not_called()
        self.assertEqual(json.loads(self.receipt.read_text()), self.build_ids)
        self.assertFalse((self.output / 'web' / 'assemblies').exists())


class SharedModuleCacheTests(unittest.TestCase):
    def setUp(self):
        from vault._build import source_digest
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.cached = self.output / 'builds' / 'checked-shared-module'
        self.cached.mkdir(parents=True)
        self.source_files = {'source.py': 'current-common-open-module'}
        self.digest = source_digest(self.source_files)
        self.revision = {'commit': 'current', 'dirty': False}
        spec = build_api.select_spec('module', 'L', 6, 2, drawer_columns=2)
        latest = self.output / 'latest' / spec.slug
        latest.parent.mkdir(parents=True)
        latest.symlink_to(self.cached)

    def cache(self, *, source=None, git=None):
        (self.cached / 'manifest.json').write_text(json.dumps({
            'passed': True, 'checksums': {},
            'source_hash': self.digest if source is None else source,
            'git': self.revision if git is None else git,
        }))

    def request_module(self, rows, *, revision):
        config = Configuration('L', 6, 2, 'module', drawer_columns=2, drawer_rows=rows)
        receipt = self.output / f'request-{rows}.receipt'
        argv = ['vault.web_worker', '--configuration', json.dumps(config.as_dict()),
                '--output', str(self.output), '--receipt', str(receipt)]
        with patch.object(sys, 'argv', argv), \
                patch.object(build_api, 'build', return_value=self.output / 'builds' / 'fresh-module') as build, \
                patch('vault._build.source_hashes', return_value=self.source_files), \
                patch('vault._build.git_provenance', return_value=revision), \
                redirect_stdout(io.StringIO()):
            main()
        return build, json.loads(receipt.read_text())

    def test_both_drawer_layouts_reuse_the_same_current_clean_module_build(self):
        self.cache()
        for rows in (1, 2):
            with self.subTest(rows=rows):
                build, receipt = self.request_module(rows, revision=self.revision)
                build.assert_not_called()
                self.assertEqual(receipt, ['checked-shared-module'])

    def test_shared_alias_does_not_bypass_source_or_dirty_checkout_checks(self):
        for rows in (1, 2):
            for reason in ('changed-source', 'dirty-checkout', 'dirty-build', 'older-commit', 'unknown-revision'):
                with self.subTest(rows=rows, reason=reason):
                    source = 'historical-partitioned-module' if reason == 'changed-source' else self.digest
                    built = dict(self.revision, dirty=True) if reason == 'dirty-build' else self.revision
                    if reason == 'older-commit':
                        built = dict(self.revision, commit='older')
                    current = dict(self.revision, dirty=True) if reason == 'dirty-checkout' else self.revision
                    if reason == 'unknown-revision':
                        current = None
                    self.cache(source=source, git=built)
                    build, receipt = self.request_module(rows, revision=current)
                    build.assert_called_once()
                    self.assertEqual(build.call_args.args[1].drawer_rows, 1)
                    self.assertEqual(receipt, ['fresh-module'])


if __name__ == '__main__':
    unittest.main()
