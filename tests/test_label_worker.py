"""Label generation retains checked-cache and source-stability guarantees."""
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
from vault.label_config import LabelConfiguration
from vault.web_worker import main


class LabelWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.receipt = self.output / 'label.receipt'
        self.config = LabelConfiguration()
        self.sources = {'label.py': 'same-source', 'label-font.json': 'same-outlines'}
        self.git = {'commit': 'same-revision', 'dirty': False}
        self.previous = self.output / 'builds' / '20261025T010000000000Z-0123456789ab'
        self.destination = self.output / 'builds' / '20261025T020000000000Z-0123456789ab'
        self.generate = Mock(return_value=self.destination)

    def cached_build(self, *, git=None, sources=None, corrupt=False):
        self.previous.mkdir(parents=True)
        artifact = self.previous / 'label.3mf'
        artifact.write_bytes(b'checked multicolor geometry')
        (self.previous / 'manifest.json').write_text(json.dumps(dict(
            passed=True, build_id=self.previous.name,
            git=self.git if git is None else git,
            source_hash=source_digest(self.sources if sources is None else sources),
            checksums={'label.3mf': hashlib.sha256(artifact.read_bytes()).hexdigest()})))
        pointer = self.output / 'latest' / self.config.slug
        pointer.parent.mkdir(parents=True)
        pointer.symlink_to(self.previous)
        if corrupt:
            artifact.write_bytes(b'changed geometry')

    def run_worker(self, *, current=None, source_values=None):
        argv = ['vault.web_worker', '--configuration', json.dumps(self.config.as_dict()),
                '--output', str(self.output), '--receipt', str(self.receipt)]
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', argv))
            stack.enter_context(patch.dict(sys.modules, {
                'vault.label_build': SimpleNamespace(build_label=self.generate)}))
            drawer_build = stack.enter_context(patch.object(build_api, 'build'))
            drawer_spec = stack.enter_context(patch.object(build_api, 'select_spec'))
            stack.enter_context(patch('vault._build.source_hashes',
                **({'side_effect': source_values} if source_values is not None
                   else {'return_value': self.sources})))
            stack.enter_context(patch('vault._build.git_provenance',
                                     return_value=self.git if current is None else current))
            stack.enter_context(redirect_stdout(io.StringIO()))
            main()
            drawer_build.assert_not_called()
            drawer_spec.assert_not_called()
        self.assertFalse((self.output / 'web' / 'assemblies').exists())

    def test_new_label_build_receipt_uses_label_generator(self):
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)
        self.assertEqual(json.loads(self.receipt.read_text()), [self.destination.name])

    def test_only_identical_clean_checked_label_build_is_reused(self):
        self.cached_build()
        self.run_worker()
        self.generate.assert_not_called()
        self.assertEqual(json.loads(self.receipt.read_text()), [self.previous.name])

    def test_clean_s_label_is_not_reused_for_m_with_identical_text_and_colors(self):
        self.cached_build()
        self.config = LabelConfiguration(family='M')
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)
        self.assertEqual(json.loads(self.receipt.read_text()), [self.destination.name])

    def test_clean_m_label_is_not_reused_for_l_with_identical_text_and_colors(self):
        self.config = LabelConfiguration(family='M')
        self.cached_build()
        self.config = LabelConfiguration(family='L')
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)

    def test_identical_clean_large_label_reuses_its_own_family_cache(self):
        self.config = LabelConfiguration(family='L')
        self.cached_build()
        self.run_worker()
        self.generate.assert_not_called()
        self.assertEqual(json.loads(self.receipt.read_text()), [self.previous.name])

    def test_dirty_checkout_rebuilds_even_with_identical_geometry_sources(self):
        self.cached_build()
        self.run_worker(current=dict(self.git, dirty=True))
        self.generate.assert_called_once_with(self.output, self.config)
        self.assertEqual(json.loads(self.receipt.read_text()), [self.destination.name])

    def test_dirty_cached_build_is_not_reused_by_clean_checkout(self):
        self.cached_build(git=dict(self.git, dirty=True))
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)

    def test_font_source_change_invalidates_label_cache(self):
        self.cached_build(sources=self.sources | {'label-font.json': 'earlier-outlines'})
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)

    def test_corrupt_cached_3mf_is_rebuilt_without_modifying_old_build(self):
        self.cached_build(corrupt=True)
        self.run_worker()
        self.generate.assert_called_once_with(self.output, self.config)
        self.assertEqual((self.previous / 'label.3mf').read_bytes(), b'changed geometry')

    def test_source_change_during_generation_fails_and_preserves_checked_receipt(self):
        with self.assertRaisesRegex(RuntimeError, 'source changed'):
            self.run_worker(source_values=[self.sources, self.sources,
                                           self.sources | {'label-font.json': 'edited'}])
        self.assertEqual(json.loads(self.receipt.read_text()), [self.destination.name])

    def test_failed_label_generation_keeps_previous_build_and_latest_pointer(self):
        self.cached_build()
        before = (self.previous / 'label.3mf').read_bytes()
        self.generate.side_effect = ValueError('Label mesh check failed')
        with self.assertRaisesRegex(ValueError, 'mesh check failed'):
            self.run_worker(current=dict(self.git, dirty=True))
        self.assertFalse(self.receipt.exists())
        self.assertEqual((self.previous / 'label.3mf').read_bytes(), before)
        self.assertEqual((self.output / 'latest' / self.config.slug).resolve(), self.previous)


if __name__ == '__main__':
    unittest.main()
