"""Native exports survive round trips and reject wrong solid geometry."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from build123d import Box, Pos, export_step
from vault.build import _export_into
from vault.exports import check_step
from vault.spec import DEFAULT_SPEC
from vault.tessellation import load_model


class StepExportTests(unittest.TestCase):
    def test_exports_are_solids_and_reviews_load_step(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch('vault.render.render_review'):
                report = _export_into(Box(10, 20, 30), output, time.monotonic())
            self.assertIsNone(report['assembly_mesh'])  # Caller supplied no finished assembly solid.
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

    def test_finished_mesh_coordinates_match_print_to_native_metadata(self):
        import numpy as np
        import trimesh
        from vault.box import BoxSpec
        from vault.facade import FacadeSpec
        for spec in (DEFAULT_SPEC, BoxSpec(), FacadeSpec(), FacadeSpec(facade_floor=.8)):
            with self.subTest(spec=spec), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                native = Pos(2, 3, 25) * Box(10, 20, 30)
                with patch('vault.render.render_review'):
                    report = _export_into(native, output, time.monotonic(), spec, finished=native)
                metadata = report['assembly_mesh']
                preview = trimesh.load_mesh(output / metadata['path'])
                printable = trimesh.load_mesh(output / 'stl' / f'{spec.slug}.stl')
                printable.apply_transform(np.array(metadata['print_to_native']).reshape((4, 4)).T)
                np.testing.assert_allclose(printable.bounds, preview.bounds, atol=1e-5)
                expected = native.bounding_box()
                np.testing.assert_allclose(preview.bounds, [list(expected.min), list(expected.max)], atol=1e-5)
                self.assertTrue(metadata['step_roundtrip']['passed'])

    def test_rejects_changed_volume_or_position(self):
        original = Box(10, 20, 30)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'wrong.step'
            for wrong in (Box(11, 20, 30), Pos(1, 0, 0) * original):
                with self.subTest(shape=wrong):
                    export_step(wrong, path)
                    with self.assertRaisesRegex(ValueError, 'STEP round-trip failed'):
                        check_step(original, path)
