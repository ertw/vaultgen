"""Single-piece key export contract."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from build123d import Solid, import_step
from vault import key_build
from vault.key import KeySpec


class KeyBuildTests(unittest.TestCase):
    def test_export_contains_one_complete_printable_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('vault.key.build_key_parts', return_value={'key': Solid.make_box(6, 6, 30)}), \
                    patch('vault.render.render_review'):
                manifest, viewer = key_build._export_key(root, KeySpec())
            self.assertEqual(set(manifest['parts']), {'key'})
            self.assertEqual(len(import_step(root / viewer['assembly']).solids()), 1)
            report = manifest['parts']['key']
            self.assertTrue(report['stl_watertight'])
            self.assertTrue(report['stl_winding_consistent'])
            self.assertTrue(report['print_step_roundtrip']['passed'])
            self.assertEqual([p.name for p in (root / 'stl').glob('*.stl')], ['key.stl'])

    def test_single_piece_configuration_has_distinct_cache_identity(self):
        with patch.object(key_build, 'run_build') as transaction:
            key_build.build_key(Path('/tmp/key-test-output'))
        self.assertEqual(transaction.call_args.kwargs['parameters'],
                         {'part': 'snap_key', 'construction': 'single_piece'})
        self.assertEqual(transaction.call_args.kwargs['aliases'], ['latest/snap_key'])
