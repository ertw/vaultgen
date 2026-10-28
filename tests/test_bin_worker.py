"""Gridfinity jobs retain source-stability and clean checked-cache rules."""
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

from vault import build as build_api
from vault._build import source_digest
from vault.bin_config import BinConfiguration
from vault.web_worker import main


class BinWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.receipt = self.output / 'bins.receipt'
        self.config = BinConfiguration.parse({'cells': [[0, 0]]})
        self.sources = {'bin.py': 'same-geometry', 'bin_config.py': 'same-layout'}
        self.git = {'commit': 'same-revision', 'dirty': False}
        self.previous = self.output / 'builds' / '20261027T010000000000Z-0123456789ab'
        self.destination = self.output / 'builds' / '20261027T020000000000Z-0123456789ab'
        self.generate = Mock(return_value=self.destination)

    def cached_build(self, *, dirty=False, corrupt=False):
        self.previous.mkdir(parents=True)
        artifact = self.previous / 'bin.stl'
        artifact.write_bytes(b'checked bin')
        (self.previous / 'manifest.json').write_text(json.dumps({
            'passed': True, 'build_id': self.previous.name,
            'git': self.git | {'dirty': dirty}, 'source_hash': source_digest(self.sources),
            'checksums': {'bin.stl': hashlib.sha256(artifact.read_bytes()).hexdigest()}}))
        pointer = self.output / 'latest' / self.config.slug
        pointer.parent.mkdir(parents=True)
        pointer.symlink_to(self.previous)
        if corrupt:
            artifact.write_bytes(b'changed mesh')

    def run_worker(self, *, dirty=False, source_values=None):
        argv = ['vault.web_worker', '--configuration', json.dumps(self.config.as_dict()),
                '--output', str(self.output), '--receipt', str(self.receipt)]
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', argv))
            stack.enter_context(patch.dict(sys.modules, {
                'vault.bin_build': SimpleNamespace(build_bins=self.generate)}))
            drawer_build = stack.enter_context(patch.object(build_api, 'build'))
            drawer_spec = stack.enter_context(patch.object(build_api, 'select_spec'))
            stack.enter_context(patch('vault._build.source_hashes',
                **({'side_effect': source_values} if source_values is not None
                   else {'return_value': self.sources})))
            stack.enter_context(patch('vault._build.git_provenance', return_value=self.git | {'dirty': dirty}))
            stack.enter_context(redirect_stdout(io.StringIO()))
            main()
            drawer_build.assert_not_called()
            drawer_spec.assert_not_called()
        self.assertFalse((self.output / 'web' / 'assemblies').exists())

    def test_new_bin_generation_records_checked_build(self):
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)
        self.assertEqual(json.loads(self.receipt.read_text()), [self.destination.name])

    def test_identical_clean_checked_bin_is_reused(self):
        self.cached_build()
        self.run_worker()
        self.generate.assert_not_called()
        self.assertEqual(json.loads(self.receipt.read_text()), [self.previous.name])

    def test_dirty_checkout_rebuilds(self):
        self.cached_build()
        self.run_worker(dirty=True)
        self.generate.assert_called_once_with(self.output, self.config)

    def test_dirty_cached_build_rebuilds(self):
        self.cached_build(dirty=True)
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)

    def test_corrupt_cached_mesh_rebuilds_without_rewriting_history(self):
        self.cached_build(corrupt=True)
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)
        self.assertEqual((self.previous / 'bin.stl').read_bytes(), b'changed mesh')

    def test_wall_variant_uses_its_own_cache(self):
        self.cached_build()
        self.config = BinConfiguration.parse(self.config.as_dict() | {'wall_pattern': 'miura', 'wall_perimeters': 1})
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)

    def test_source_change_fails_and_keeps_checked_receipt(self):
        with self.assertRaisesRegex(RuntimeError, 'source changed'):
            self.run_worker(source_values=[self.sources, self.sources,
                self.sources | {'bin.py': 'changed-geometry'}])
        self.assertEqual(json.loads(self.receipt.read_text()), [self.destination.name])


if __name__ == '__main__':
    unittest.main()
