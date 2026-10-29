"""Facade color separation must preserve the skin, interfaces and registration."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from vault._build import verify_files
from vault.build import build, print_orientation
from vault.exports import precise_volume
from vault.facade import FacadeSpec, build_facade
from vault.facade_markings import build_facade_materials, MARK_CENTERS


class FacadeMarkingTests(unittest.TestCase):
    def test_material_partition_across_sizes_and_floors(self):
        for family, height, floor in [('S', 1, .8), ('M', 2, 'default'), ('L', 2, .8)]:
            with self.subTest(family=family, height=height, floor=floor):
                spec = FacadeSpec(family, height, floor)
                original = build_facade(spec=spec)
                materials = build_facade_materials(original)
                self.assertEqual({k: v['role'] for k, v in materials.items()},
                                 {'body': 'primary', 'locked': 'secondary', 'unlocked': 'secondary'})
                shapes = [part['shape'] for part in materials.values()]
                self.assertAlmostEqual(sum(precise_volume(s) for s in shapes),
                                       precise_volume(original), delta=.001)
                for i, shape in enumerate(shapes):
                    for other in shapes[i+1:]:
                        self.assertLess(sum(abs(precise_volume(s)) for s in shape.intersect(other) or []), 1e-6)
                body = materials['body']['shape']
                for name, (x, z) in MARK_CENTERS.items():
                    self.assertTrue(original.is_inside((x, 9.9, z - 1)))
                    self.assertFalse(body.is_inside((x, 9.9, z - 1)))
                    self.assertTrue(body.is_inside((x, 9.3, z - 1)))
                    icon = materials[name]['shape']
                    self.assertTrue(icon.is_inside((x, 9.9, z - 1)))
                    self.assertAlmostEqual(icon.bounding_box().max.Y, 10.)
                    self.assertAlmostEqual(print_orientation(icon, spec).bounding_box().min.Z,
                                           0 if floor == .8 else 9.4, places=6)
                # The closed shackle joins both shoulders; the open one has a gap.
                for name in ('locked', 'unlocked'):
                    x, z = MARK_CENTERS[name]
                    self.assertEqual(materials[name]['shape'].is_inside((x + 1.4, 9.7, z + .7)),
                                     name == 'locked')

    def test_checked_build_and_failed_color_export_preserve_history(self):
        spec = FacadeSpec(facade_floor=.8)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = build(root, spec)
            manifest = verify_files(destination)
            self.assertTrue(manifest['multicolor_roundtrip']['passed'])
            self.assertEqual(manifest['multicolor_roundtrip']['colors'], 2)
            self.assertEqual(manifest['multicolor_roundtrip']['registered_components'], 3)
            self.assertEqual(manifest['multicolor_roundtrip']['build_items'], 1)
            self.assertIn(manifest['multicolor_3mf'], manifest['checksums'])
            self.assertEqual(len(manifest['parts']), 1)
            for name, material in manifest['parts'][spec.slug]['materials'].items():
                self.assertTrue(material['step_roundtrip']['passed'])
                self.assertTrue(material['print_step_roundtrip']['passed'])
                self.assertTrue(material['stl_watertight'])
                self.assertIn(material['assembly_mesh']['path'], manifest['checksums'])
                self.assertIn(material['print_path'], manifest['checksums'])
            previous = (root / 'latest-successful').resolve()
            with patch('vault.facade_build._write_3mf', side_effect=ValueError('bad color export')):
                with self.assertRaisesRegex(ValueError, 'bad color export'):
                    build(root, spec)
            self.assertEqual((root / 'latest-successful').resolve(), previous)
            verify_files(destination)
