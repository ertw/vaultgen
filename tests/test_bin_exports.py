"""Container export checks and publication preserve immutable build history."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import trimesh

from vault._build import verify_files
from vault.bin_build import build_bins
from vault.bin_config import BinConfiguration


class BinExportTests(unittest.TestCase):
    def test_drawer_box_exports_flat_base_instructions_and_actual_material_metrics(self):
        config = BinConfiguration(container_type='drawer',cells=((0,0),),wall_perimeters=2)
        with TemporaryDirectory() as directory:
            built = build_bins(Path(directory),config)
            manifest = verify_files(built)
            self.assertEqual(manifest['gridfinity_configuration'],config.as_dict())
            self.assertEqual(manifest['gridfinity_layout']['foot_height_mm'],0)
            self.assertGreater(manifest['design_metrics']['material_volume_cm3'],0)
            self.assertAlmostEqual(manifest['design_metrics']['clear_height_mm'],config.height_mm-1.2)
            self.assertIn('flat base',(built/'printing.txt').read_text())
            self.assertIn('plain Vault drawer',(built/'printing.txt').read_text())
            self.assertTrue(manifest['parts']['bin_01']['stl_watertight'])

    def test_disconnected_containers_export_checked_print_files_and_keep_history(self):
        config = BinConfiguration.parse({
            'cells': [[0, 0], [1, 0], [2, 2]],
            'dividers': [{'axis': 'x', 'x': 1, 'y': 0}], 'wall_perimeters': 1})
        with TemporaryDirectory() as directory:
            root = Path(directory)
            built = build_bins(root, config)
            manifest = verify_files(built)
            self.assertEqual(len(manifest['parts']), 2)
            self.assertTrue(manifest['step_roundtrip']['passed'])
            self.assertEqual(manifest['gridfinity_configuration'], config.as_dict())
            self.assertIn('gridfinity_layout', manifest)
            for name, report in manifest['parts'].items():
                self.assertTrue(report['cad_valid'])
                self.assertEqual(report['solids'], 1)
                self.assertEqual(report['boundary_shells'], 1)
                self.assertTrue(report['step_roundtrip']['passed'])
                self.assertTrue(report['print_step_roundtrip']['passed'])
                mesh = trimesh.load_mesh(built / 'stl' / f'{name}.stl')
                self.assertTrue(mesh.is_watertight)
                self.assertTrue(mesh.is_winding_consistent)
                self.assertGreater(mesh.volume, 0)
                self.assertAlmostEqual(mesh.bounds[0, 2], 0, places=5)
            parameters = json.loads((built / 'resolved-parameters.json').read_text())
            self.assertEqual(parameters['gridfinity_configuration'], config.as_dict())
            previous = (root / 'latest-successful').resolve()
            with patch('vault.bin_build._export_bins', side_effect=ValueError('bad bin mesh')):
                with self.assertRaisesRegex(ValueError, 'bad bin mesh'):
                    build_bins(root, config)
            self.assertEqual((root / 'latest-successful').resolve(), previous)
            self.assertEqual((root / 'latest' / config.slug).resolve(), previous)
            self.assertEqual(len(list((root / 'builds').iterdir())), 1)
            verify_files(built)


if __name__ == '__main__':
    unittest.main()
