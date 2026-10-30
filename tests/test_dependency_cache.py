"""Dependency-aware reuse preserves immutable exports and revision safeguards."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from vault._build import source_digest
from vault.key import KeySpec


PARAMETERS = {'part': 'snap_key', 'construction': 'single_piece'}


class DependencyCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from vault.dependencies import fingerprint
        cls.expected = fingerprint('key', PARAMETERS, toolchain={'fixture': 'runtime'})

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.current = {'commit': 'current-commit', 'dirty': False}
        self.sources = {'source.py': 'whole-project-now'}
        self.digest = source_digest(self.sources)
        self.spec = KeySpec()

    def candidate(self, number, *, dependencies=True, git=None, source=None,
                  parameters=None, corrupt=False, latest=False):
        directory = self.output / 'builds' / f'20261030T010000{number:06d}Z-0123456789ab'
        directory.mkdir(parents=True)
        artifact = directory / 'key.step'
        artifact.write_bytes(b'checked immutable CAD')
        resolved = directory / 'resolved-parameters.json'
        resolved.write_text(json.dumps(PARAMETERS if parameters is None else parameters))
        manifest = {
            'passed': True, 'build_id': directory.name,
            'git': {'commit': 'older-commit', 'dirty': False} if git is None else git,
            'source_hash': 'older-whole-project' if source is None else source,
            'checksums': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (artifact, resolved)},
        }
        if dependencies:
            manifest['dependencies'] = deepcopy(self.expected)
            dependency_file = directory / 'dependencies.json'
            dependency_file.write_text(json.dumps(manifest['dependencies']))
            manifest['checksums'][dependency_file.name] = hashlib.sha256(dependency_file.read_bytes()).hexdigest()
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        if latest:
            pointer = self.output / 'latest' / self.spec.slug
            pointer.parent.mkdir(parents=True, exist_ok=True)
            pointer.unlink(missing_ok=True)
            pointer.symlink_to(directory)
        if corrupt:
            artifact.write_bytes(b'corrupted CAD')
        return directory

    def lookup(self, *, current=None):
        from vault.build_cache import find_reusable
        return find_reusable(self.output, self.spec, self.expected, self.digest,
                             self.current if current is None else current)

    def test_unchanged_dependencies_reuse_build_from_older_clean_commit(self):
        previous = self.candidate(1, latest=True)
        destination, _ = self.lookup()
        self.assertEqual(destination, previous)

    def test_history_lookup_recovers_older_matching_build_without_rewriting_latest(self):
        previous = self.candidate(1)
        newest = self.candidate(2, latest=True, corrupt=True)
        before = (newest / 'key.step').read_bytes()
        destination, _ = self.lookup()
        self.assertEqual(destination, previous)
        self.assertEqual((self.output / 'latest' / self.spec.slug).resolve(), newest)
        self.assertEqual((newest / 'key.step').read_bytes(), before)

    def test_wrong_resolved_configuration_is_not_accepted_even_with_matching_digest(self):
        self.candidate(1, latest=True, parameters=PARAMETERS | {'construction': 'old_two_piece'})
        self.assertIsNone(self.lookup()[0])

    def test_dirty_checkout_and_dirty_build_cannot_reuse_matching_dependencies(self):
        previous = self.candidate(1, latest=True)
        self.assertIsNone(self.lookup(current=self.current | {'dirty': True})[0])
        manifest_path = previous / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['git']['dirty'] = True
        manifest_path.write_text(json.dumps(manifest))
        self.assertIsNone(self.lookup()[0])

    def test_unknown_cached_revision_is_not_reused(self):
        self.candidate(1, latest=True, git={})
        self.assertIsNone(self.lookup()[0])

    def test_changed_dependency_record_does_not_reuse_old_digest(self):
        previous = self.candidate(1, latest=True)
        path = previous / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['dependencies']['source_files']['src/vault/key_geometry.py'] = 'edited'
        path.write_text(json.dumps(manifest))
        self.assertIsNone(self.lookup()[0])

    def test_malformed_dependency_metadata_is_skipped_in_favor_of_checked_history(self):
        previous = self.candidate(1)
        newest = self.candidate(2, latest=True)
        path = newest / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['dependencies']['source_files'] = ['malformed']
        path.write_text(json.dumps(manifest))
        self.assertEqual(self.lookup()[0], previous)

    def test_malformed_manifest_is_skipped_in_favor_of_checked_history(self):
        previous = self.candidate(1)
        newest = self.candidate(2, latest=True)
        (newest / 'manifest.json').write_text('[]')
        self.assertEqual(self.lookup()[0], previous)

    def test_corrupt_candidate_has_explanation_and_never_becomes_reusable(self):
        self.candidate(1, latest=True, corrupt=True)
        destination, reasons = self.lookup()
        self.assertIsNone(destination)
        self.assertTrue(reasons)

    def test_legacy_latest_requires_exact_whole_source_and_revision(self):
        previous = self.candidate(1, dependencies=False, latest=True,
                                  git=self.current, source=self.digest)
        self.assertEqual(self.lookup()[0], previous)
        path = previous / 'manifest.json'
        manifest = json.loads(path.read_text())
        for changed in ({'source_hash': 'other-source'},
                        {'git': {'commit': 'old', 'dirty': False}},
                        {'git': self.current | {'dirty': True}}):
            with self.subTest(changed=changed):
                path.write_text(json.dumps(manifest | changed))
                self.assertIsNone(self.lookup()[0])

    def test_legacy_build_from_history_is_not_guessed_to_match_a_part(self):
        self.candidate(1, dependencies=False, git=self.current, source=self.digest)
        self.assertIsNone(self.lookup()[0])

    def test_incomplete_dependency_graph_cannot_enable_cross_revision_reuse(self):
        from vault.build_cache import compatible
        expected = deepcopy(self.expected)
        expected['reusable'] = False
        expected['reasons'] = ['Unknown dynamic input']
        accepted, reasons = compatible({'dependencies': expected}, expected)
        self.assertFalse(accepted)
        self.assertTrue(reasons)

    def test_worker_reuses_clean_older_key_and_records_cache_reason(self):
        from vault.build_events import PREFIX, event_output
        from vault.generator import Configuration
        from vault.web_worker import _build_part
        previous = self.candidate(1, latest=True)
        output = io.StringIO()
        with patch('vault._build.source_hashes', return_value=self.sources), \
                patch('vault._build.git_provenance', return_value=self.current), \
                patch('vault.build_cache.expected_for_spec', return_value=self.expected), \
                patch('vault.build.build') as generate, redirect_stdout(output), event_output():
            result = _build_part(Configuration(part='key'), 'key', self.output, self.digest)
        self.assertEqual(result, previous.name)
        generate.assert_not_called()
        events = [json.loads(line[len(PREFIX):]) for line in output.getvalue().splitlines()
                  if line.startswith(PREFIX)]
        decision = next(event for event in events if event['event'] == 'cache_decision')
        self.assertTrue(decision['reused'])
        self.assertTrue(decision['reasons'])
        self.assertEqual(decision['dependency_digest'], self.expected['digest'])

    def validate_accessory(self, previous, *, expected=None, current=None):
        """Exercise the strict component-source gate without constructing CAD."""
        from vault.generator import Configuration
        from vault.web_worker import _validate_set
        config = Configuration(part='key')
        with patch('vault._build.source_hashes', return_value=self.sources), \
                patch('vault._build.git_provenance', return_value=self.current if current is None else current), \
                patch('vault.build_cache.expected_for_spec', return_value=expected or self.expected), \
                patch('vault.assembly_validation.validation_signature', return_value='validator-signature'), \
                patch('vault.assembly_validation.validate_assembly', return_value={'passed': True}) as validator, \
                redirect_stdout(io.StringIO()):
            _validate_set(config, [previous.name], self.output, self.digest, 'set-receipt',
                          strict_sources=True)
        return validator

    def test_strict_assembly_accepts_compatible_accessory_from_older_clean_source(self):
        previous = self.candidate(1)
        validator = self.validate_accessory(previous)
        validator.assert_called_once()
        receipt = json.loads((self.output / 'web/assemblies/set-receipt.json').read_text())
        self.assertEqual(receipt['accessory_build_ids'], [previous.name])
        self.assertEqual(receipt['component_dependencies'], {'key': self.expected['digest']})

    def test_strict_assembly_rejects_changed_accessory_dependencies(self):
        previous = self.candidate(1)
        expected = deepcopy(self.expected)
        expected['source_files']['src/vault/key_geometry.py'] = 'new-geometry'
        with self.assertRaisesRegex(RuntimeError, 'dependencies changed'):
            self.validate_accessory(previous, expected=expected)
        self.assertFalse((self.output / 'web/assemblies/set-receipt.json').exists())

    def test_strict_assembly_rejects_cross_source_reuse_in_dirty_checkout(self):
        previous = self.candidate(1)
        with self.assertRaisesRegex(RuntimeError, 'clean Git'):
            self.validate_accessory(previous, current=self.current | {'dirty': True})

    def test_strict_assembly_accepts_fresh_dirty_build_with_same_pinned_source(self):
        previous = self.candidate(1, git=self.current | {'dirty': True}, source=self.digest)
        validator = self.validate_accessory(previous, current=self.current | {'dirty': True})
        validator.assert_called_once()

    def uncertain_dependencies(self):
        from vault.dependencies import fingerprint_digest
        record = deepcopy(self.expected)
        record.update(reusable=False, reasons=['Unknown dynamic input'])
        record['digest'] = fingerprint_digest(record)
        return record

    def test_strict_assembly_allows_uncertain_graph_for_same_pinned_source(self):
        expected = self.uncertain_dependencies()
        with patch.object(self, 'expected', expected):
            previous = self.candidate(1, source=self.digest)
            validator = self.validate_accessory(previous)
        validator.assert_called_once()

    def test_strict_assembly_rejects_uncertain_graph_from_other_source(self):
        expected = self.uncertain_dependencies()
        with patch.object(self, 'expected', expected):
            previous = self.candidate(1)
            with self.assertRaisesRegex(RuntimeError, 'Unknown dynamic input'):
                self.validate_accessory(previous)


class DependencyPublicationTests(unittest.TestCase):
    def test_normal_export_transaction_records_dependency_graph_in_immutable_manifest(self):
        from vault._build import run_build, verify_files
        from vault.project import PROJECT_ROOT
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            def generate(state):
                (state.stage / 'key.step').write_bytes(b'checked export fixture')
                return {'passed': True}, {'assembly': 'key.step', 'components': []}
            configuration_hash = hashlib.sha256(json.dumps(PARAMETERS, sort_keys=True).encode()).hexdigest()
            try:
                with redirect_stdout(io.StringIO()):
                    directory = run_build(PROJECT_ROOT, configuration_hash, generate,
                                          parameters=PARAMETERS, output=output,
                                          aliases=['latest/snap_key'])
                manifest = verify_files(directory)
                record = manifest['dependencies']
                self.assertEqual(record['kind'], 'key')
                self.assertEqual(record['parameters'], PARAMETERS)
                self.assertIn('src/vault/key_geometry.py', record['source_files'])
                self.assertIn('edges', record)
                self.assertIn('toolchain', record)
                self.assertEqual((output / 'latest/snap_key').resolve(), directory)
            finally:
                for path in output.rglob('*'):
                    if not path.is_symlink():
                        path.chmod(0o755 if path.is_dir() else 0o644)

    def test_dependency_or_toolchain_change_during_export_preserves_previous_success(self):
        from vault._build import run_build, verify_files
        from vault.dependencies import fingerprint_digest
        before = {'schema': 'vault-dependencies/v1', 'kind': 'key', 'parameters': PARAMETERS,
                  'source_files': {'src/vault/fixture.py': 'before'}, 'edges': {},
                  'toolchain': {'fixture': 'before'}, 'reusable': True, 'reasons': []}
        before['digest'] = fingerprint_digest(before)
        for field in ('source_files', 'toolchain'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = root / 'src/vault/fixture.py'
                fixture.parent.mkdir(parents=True)
                fixture.write_text('pass\n')
                output = root / 'out'
                def generate(state):
                    (state.stage / 'key.step').write_bytes(b'checked export fixture')
                    return {'passed': True}, {'assembly': 'key.step', 'components': []}
                after = deepcopy(before)
                after[field] = {**after[field], 'changed': 'after'}
                after['digest'] = fingerprint_digest(after)
                try:
                    with patch('vault.dependencies.fingerprint', return_value=before), \
                            redirect_stdout(io.StringIO()):
                        previous = run_build(root, 'configuration', generate, parameters=PARAMETERS,
                                             output=output, aliases=['latest/snap_key'])
                    original_manifest = verify_files(previous)
                    with patch('vault.dependencies.fingerprint', side_effect=[before, after]), \
                            redirect_stdout(io.StringIO()), \
                            self.assertRaisesRegex(RuntimeError, 'dependencies or toolchain changed'):
                        run_build(root, 'configuration', generate, parameters=PARAMETERS,
                                  output=output, aliases=['latest/snap_key'])
                    self.assertEqual((output / 'latest/snap_key').resolve(), previous)
                    self.assertEqual((output / 'latest-successful').resolve(), previous)
                    self.assertEqual(verify_files(previous), original_manifest)
                    self.assertEqual(list((output / 'builds').iterdir()), [previous])
                    failures = list((output / 'failed').glob('*/failure.json'))
                    self.assertEqual(len(failures), 1)
                    self.assertIn('dependencies or toolchain changed', json.loads(failures[0].read_text())['error'])
                finally:
                    for path in root.rglob('*'):
                        if not path.is_symlink():
                            path.chmod(0o755 if path.is_dir() else 0o644)


class BuildParameterContractTests(unittest.TestCase):
    def test_cache_parameters_match_actual_publication_for_every_part_group(self):
        from vault import build as builds, key_build, label_build, bin_build
        from vault.bin_config import BinConfiguration
        from vault.generator import ACCESSORY_PARTS, ASSEMBLY_PARTS
        from vault.label_config import LabelConfiguration
        from vault.spec import ModuleSpec
        output = Path('/tmp/vault-parameter-contract-fixture')
        cases = []
        for kind in (*ASSEMBLY_PARTS, *ACCESSORY_PARTS):
            for family, depth, height in (('S', 3, 1), ('L', 7, 4)):
                spec = builds.select_spec(kind, family, depth, height)
                cases.append((f'{kind}:{family}{depth}/{height}', spec,
                              lambda spec=spec: builds.build(output, spec)))
        # These cases exercise the geometry identities that differ from the
        # request's drawer layout and the optional wall/floor selections.
        variants = [ModuleSpec('L', 6, 2, drawer_columns=2, drawer_rows=2)]
        for kind in ('module', 'box', 'facade'):
            variants.append(builds.select_spec(kind, 'L', 6, 2, drawer_columns=2, drawer_rows=2,
                box_variant='gridfinity', box_floor=0, facade_floor=.8,
                wall_pattern='miura', wall_perimeters=1, nozzle_size=.8))
        for spec in variants:
            cases.append((spec.slug, spec, lambda spec=spec: builds.build(output, spec)))
        key_spec = KeySpec()
        cases.append(('direct-key', key_spec, lambda: key_build.build_key(output)))
        for family in ('S', 'L'):
            label = LabelConfiguration(family=family)
            cases.append((f'label:{family}', label,
                          lambda label=label: label_build.build_label(output, label)))
            for container in ('gridfinity', 'drawer'):
                bins = BinConfiguration(family=family, cells=((0, 0),), container_type=container)
                cases.append((f'bins:{family}:{container}', bins,
                              lambda bins=bins: bin_build.build_bins(output, bins)))
        transaction = Mock(return_value=output / 'builds/fixture')
        with patch('vault._build.run_build', transaction), \
                patch.object(builds, 'run_build', transaction), \
                patch.object(key_build, 'run_build', transaction), \
                patch.object(label_build, 'run_build', transaction), \
                patch.object(bin_build, 'run_build', transaction):
            for name, spec, publish in cases:
                with self.subTest(part=name):
                    transaction.reset_mock()
                    publish()
                    transaction.assert_called_once()
                    self.assertEqual(transaction.call_args.kwargs['parameters'], builds.build_parameters(spec))


if __name__ == '__main__':
    unittest.main()
