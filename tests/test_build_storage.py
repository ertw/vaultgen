"""Vault uses the shared transaction and retains earlier configurations."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vault import __main__ as cli
from vault.spec import DEFAULT_SPEC


class StorageTests(unittest.TestCase):
    def test_build_history_failure_and_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def export(stage, spec):
                data = b'solid'
                (stage / f'{spec.slug}.step').write_bytes(data)
                return {'cad_valid': True, 'solids': 1, 'boundary_shells': 1,
                        'step_roundtrip': {'passed': True},
                        'print_step_roundtrip': {'passed': True}, 'step_bytes': len(data),
                        'files': {f'{spec.slug}.step': hashlib.sha256(data).hexdigest()}}

            try:
                with patch.object(cli, 'PROJECT_ROOT', root), patch.object(cli, '_build_into', export):
                    first = cli.build(root / 'out')
                    second = cli.build(root / 'out')
                    self.assertNotEqual(first, second)
                    self.assertEqual(cli.selected_build(root / 'out', DEFAULT_SPEC), second)
                    self.assertEqual(json.loads((first / 'manifest.json').read_text())['schema'], 'cad-build-v1')
                    with patch.object(cli, '_build_into', side_effect=ValueError('geometry failed')):
                        with self.assertRaises(ValueError):
                            cli.build(root / 'out')
                    def rejected(stage, spec):
                        report = export(stage, spec)
                        report['print_step_roundtrip']['passed'] = False
                        return report
                    with patch.object(cli, '_build_into', rejected):
                        with self.assertRaisesRegex(ValueError, 'STEP validation'):
                            cli.build(root / 'out')
                    self.assertEqual(cli.selected_build(root / 'out', DEFAULT_SPEC), second)
                    self.assertEqual((root / 'out/latest-successful').resolve(), second)
            finally:
                for path in root.rglob('*'):
                    if not path.is_symlink():
                        path.chmod(0o755 if path.is_dir() else 0o644)


if __name__ == '__main__':
    unittest.main()
