"""Native exports survive round trips and reject wrong solid geometry."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from build123d import Box, Pos, export_step
from vault.__main__ import _export_into
from vault.exports import check_step
from vault.spec import DEFAULT_SPEC
from vault.tessellation import load_model


class StepExportTests(unittest.TestCase):
    def test_exports_are_solids_and_reviews_load_step(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch('vault.render.render_review'):
                report = _export_into(Box(10, 20, 30), output, time.monotonic())
            self.assertTrue(report['step_roundtrip']['passed'])
            self.assertTrue(report['print_step_roundtrip']['passed'])
            self.assertEqual(sorted(p.suffix for p in output.glob(DEFAULT_SPEC.slug + '*')),
                             ['.brep', '.step', '.step'])
            import trimesh
            from vault.model import print_orientation
            mesh_path = output / 'stl' / f'{DEFAULT_SPEC.slug}.stl'
            printable = trimesh.load_mesh(mesh_path)
            self.assertTrue(printable.is_watertight)
            self.assertTrue(printable.is_winding_consistent)
            self.assertAlmostEqual(printable.volume, 6000)
            expected = print_orientation(Box(10, 20, 30)).bounding_box()
            for actual, target in zip(printable.bounds.flatten(), [*expected.min, *expected.max]):
                self.assertAlmostEqual(actual, target, places=4)
            mesh = load_model(output / f'{DEFAULT_SPEC.slug}.step')
            self.assertTrue(mesh.is_watertight)
            self.assertAlmostEqual(mesh.volume, 6000)

    def test_rejects_changed_volume_or_position(self):
        original = Box(10, 20, 30)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'wrong.step'
            for wrong in (Box(11, 20, 30), Pos(1, 0, 0) * original):
                with self.subTest(shape=wrong):
                    export_step(wrong, path)
                    with self.assertRaisesRegex(ValueError, 'STEP round-trip failed'):
                        check_step(original, path)
