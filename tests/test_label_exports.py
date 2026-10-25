"""Checked multipart exports must preserve positions and immutable history."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import trimesh

from vault._build import verify_files
from vault.label_build import build_label
from vault.label_config import LabelConfiguration


class LabelExportTests(unittest.TestCase):
    def test_checked_multicolor_build_and_failed_export_preserve_history(self):
        config = LabelConfiguration(family='L',lines=[{'text':'B8 YY','size':6,'color':'#ffffff'},
                                          {'text':'gyp íì','size':4,'color':'#ff0000'}])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            built = build_label(root,config)
            manifest = verify_files(built)
            self.assertEqual(manifest['multicolor_roundtrip']['colors'],3)
            self.assertTrue(manifest['geometry_check']['passed'])
            self.assertEqual(len(manifest['parts']),3)
            self.assertEqual(manifest['label_configuration']['family'],'L')
            self.assertEqual(manifest['label_dimensions']['width_mm'],129.4)
            self.assertTrue(any(name.endswith('label-font.json') for name in manifest['source_files']))
            three_mf = built/manifest['multicolor_3mf']
            self.assertIn(three_mf.name,manifest['checksums'])
            with ZipFile(three_mf) as package:
                self.assertIn('3D/3dmodel.model',package.namelist())
            positions = []
            for name,report in manifest['parts'].items():
                self.assertTrue(report['step_roundtrip']['passed'])
                self.assertTrue(report['print_step_roundtrip']['passed'])
                mesh = trimesh.load_mesh(built/'stl'/f'{name}.stl')
                self.assertTrue(mesh.is_watertight)
                self.assertTrue(mesh.is_winding_consistent)
                self.assertGreater(mesh.volume,0)
                self.assertAlmostEqual(mesh.bounds[0,2],0.,places=5)
                if name == 'label_body':
                    self.assertAlmostEqual(mesh.bounds[0,0],0.,places=5)
                    # Binary STL stores float32 vertices; 129.4 rounds down by
                    # 0.0000061 mm despite the native/STEP width being exact.
                    self.assertAlmostEqual(mesh.bounds[1,0],129.4,delta=1e-4)
                positions.append(mesh.bounds[0,0])
            self.assertGreater(positions[1],3)
            params = json.loads((built/'resolved-parameters.json').read_text())
            self.assertEqual(params['label_configuration'],config.as_dict())
            self.assertTrue(params['part'].endswith('_label'))
            previous = (root/'latest-successful').resolve()
            with patch('vault.label_build._export_label',side_effect=ValueError('bad label export')):
                with self.assertRaisesRegex(ValueError,'bad label export'):
                    build_label(root,config)
            self.assertEqual((root/'latest-successful').resolve(),previous)
            self.assertEqual(len(list((root/'builds').iterdir())),1)
            self.assertEqual(len(list((root/'failed').iterdir())),1)
            verify_files(built)


if __name__ == '__main__':
    unittest.main()
