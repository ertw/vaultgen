"""Saved previews distinguish changed inputs from unrelated source revisions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vault.dependencies import fingerprint, fingerprint_digest
from vault.generator import Configuration
from vault.web_builds import BuildFiles, freshness


PARAMETERS = {'part': 'snap_key', 'construction': 'single_piece'}
CURRENT = {'commit': 'new', 'dirty': False}


class DependencyFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = fingerprint('key', PARAMETERS, toolchain={'fixture': 'runtime'})

    def manifest(self):
        return {'git': {'commit': 'old', 'dirty': False},
                'dependencies': deepcopy(self.record)}

    def check(self, manifest=None, current=CURRENT, expected=None):
        with patch('vault.dependencies.fingerprint', return_value=expected or self.record):
            return freshness(manifest or self.manifest(), current)

    def test_older_clean_revision_is_fresh_when_dependencies_match(self):
        result = self.check()
        self.assertFalse(result['warning'])
        self.assertTrue(result['dependencies_match'])
        self.assertEqual(result['dependency_digest'], self.record['digest'])
        self.assertEqual(result['commit'], 'old')

    def test_changed_geometry_reports_the_specific_dependency(self):
        expected = deepcopy(self.record)
        expected['source_files']['src/vault/key_geometry.py'] = 'new-geometry'
        expected['digest'] = fingerprint_digest(expected)
        result = self.check(expected=expected)
        self.assertTrue(result['warning'])
        self.assertFalse(result['dependencies_match'])
        self.assertIn('src/vault/key_geometry.py', ' '.join(result['reasons']))

    def test_dependency_match_does_not_hide_dirty_or_unknown_provenance(self):
        for current in (None, {}, CURRENT | {'dirty': True}):
            with self.subTest(current=current):
                self.assertTrue(self.check(current=current)['warning'])
        for git in ({}, {'commit': 'old', 'dirty': True}):
            with self.subTest(git=git):
                self.assertTrue(self.check(self.manifest() | {'git': git})['warning'])

    def test_malformed_dependency_record_warns_instead_of_breaking_history(self):
        for record in (None, [], {}, {'kind': 'key', 'parameters': {}},
                       self.record | {'source_files': []}):
            with self.subTest(record=record):
                result = self.check(self.manifest() | {'dependencies': record})
                self.assertTrue(result['warning'])

    def test_legacy_record_still_requires_same_clean_commit(self):
        with patch('vault.dependencies.fingerprint') as graph:
            self.assertTrue(freshness({'git': {'commit': 'old', 'dirty': False}}, CURRENT)['warning'])
            self.assertFalse(freshness({'git': CURRENT}, CURRENT)['warning'])
        graph.assert_not_called()

    def write_build(self, root, number, *, record=None, source='source', component=False):
        build_id = f'20261030T010000{number:06d}Z-0123456789ab'
        directory = root / 'builds' / build_id
        directory.mkdir(parents=True)
        (directory / 'resolved-parameters.json').write_text(json.dumps(PARAMETERS))
        parts = {} if not component else {'key': {'assembly_mesh': {
            'schema': 'vault-assembly-mesh/v1', 'coordinates': 'native',
            'finished': True, 'component': 'key', 'path': 'preview/key.stl'}}}
        manifest = self.manifest() | {'passed': True, 'build_id': build_id,
            'source_hash': source, 'parts': parts, 'checksums': {'preview/key.stl': 'fixture'}}
        if record is not None:
            manifest['dependencies'] = record
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        return build_id

    def test_history_reuses_graph_calculation_within_one_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_build(root, 1)
            self.write_build(root, 2)
            with patch('vault.dependencies.fingerprint', return_value=self.record) as graph:
                history = BuildFiles(root).history(CURRENT)
                self.assertEqual(len(history), 2)
                self.assertEqual(graph.call_count, 1)
                BuildFiles(root).history(CURRENT)
                self.assertEqual(graph.call_count, 2)

    def test_assembly_prefers_compatible_history_over_newer_stale_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            older = self.write_build(root, 1, component=True)
            stale = deepcopy(self.record)
            stale['source_files']['src/vault/key_geometry.py'] = 'different-geometry'
            stale['digest'] = fingerprint_digest(stale)
            self.write_build(root, 2, record=stale, component=True)
            with patch('vault.dependencies.fingerprint', return_value=self.record), \
                    patch('vault.web_builds.git_provenance', return_value=CURRENT):
                scene = BuildFiles(root).assembly(Configuration())
            self.assertEqual([item['build_id'] for item in scene['instances']], [older])

    def test_compatible_mixed_source_snapshots_do_not_raise_revision_warning(self):
        from vault.assembly import assembly_definition
        definition = assembly_definition(Configuration())
        # Supply the full scene through history; only freshness and source
        # provenance affect whether mixed snapshots deserve a warning here.
        records = []
        for index, kind in enumerate(dict.fromkeys(item['kind'] for item in definition['instances'])):
            components = list(dict.fromkeys(item['component'] for item in definition['instances'] if item['kind'] == kind))
            records.append({'id': f'build-{kind}', 'kind': kind,
                'legacy_partitioned_module': False,
                'configuration': {'family': 'S', 'depth_units': 4, 'height_units': 1},
                'source_hash': f'source-{index}',
                'freshness': {'reasons': [], 'warning': False, 'dependencies_match': True},
                'parts': [{'assembly_mesh': {'component': component}, 'assembly_url': '/fixture.stl'}
                          for component in components]})
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(BuildFiles, 'history', return_value=records):
            files = BuildFiles(temporary)
            scene = files.assembly(Configuration())
            self.assertFalse(any('different source revisions' in warning for warning in scene['warnings']))
            records[0]['freshness']['dependencies_match'] = None
            scene = files.assembly(Configuration())
            self.assertTrue(any('different source revisions' in warning for warning in scene['warnings']))


if __name__ == '__main__':
    unittest.main()
