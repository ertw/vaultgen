"""The key export preserves print orientations and assembled component positions."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from build123d import Compound, Solid, import_step
from vault import key_build


@dataclass(frozen=True)
class _Dimensions:
    clearance: float = .2


@dataclass(frozen=True)
class _Spec:
    slug: str = 'snap_key'
    name: str = 'Snap-fit Key'


def _key_module(*, overlap=False):
    """Small solids keep tests about export contracts independent of key design."""
    module = ModuleType('vault.key')
    module.KeyDimensions, module.KeySpec = _Dimensions, _Spec

    def parts(dimensions):
        return {'gear': Solid.make_box(6, 6, 3),
                'handle': Solid.make_box(10, 4, 5)}

    def assembly(dimensions):
        shapes = parts(dimensions)
        gear = shapes['gear']
        handle = shapes['handle'].translate((-2, 1, 2 if overlap else 3))
        gear.label, handle.label = 'gear', 'handle'
        return Compound(children=[gear, handle])

    module.build_key_parts, module.build_key_assembly = parts, assembly
    return module


class KeyBuildTests(unittest.TestCase):
    def test_export_checks_print_parts_and_preserves_assembled_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict('sys.modules', {'vault.key': _key_module()}), \
                    patch('vault.render.render_review'):
                manifest, viewer = key_build._export_key(root, _Dimensions(), _Spec())
            self.assertEqual(viewer['assembly'], 'snap_key_assembled.step')
            self.assertEqual(manifest['assembly_overlap_mm3'], 0)
            self.assertTrue(manifest['assembled_step_roundtrip']['passed'])
            self.assertTrue(manifest['exploded_step_roundtrip']['passed'])
            self.assertEqual(manifest['key_dimensions'], asdict(_Dimensions()))
            self.assertEqual(json.loads((root / 'build.json').read_text()), manifest)
            assembled = import_step(root / viewer['assembly'])
            self.assertEqual(len(assembled.solids()), 2)
            by_name = {child.label: child for child in assembled.children}
            self.assertEqual(set(by_name), {'gear', 'handle'})
            self.assertAlmostEqual(by_name['handle'].bounding_box().min.Z, 3.)
            for description in (viewer, viewer['exploded'], viewer['print_layout']):
                self.assertEqual({c['name'] for c in description['components']},
                                 set(manifest['parts']))
            for component in viewer['components']:
                self.assertTrue((root / component['step']).is_file())
            for stem, report in manifest['parts'].items():
                self.assertTrue(report['stl_watertight'])
                self.assertTrue(report['stl_winding_consistent'])
                self.assertTrue((root / 'stl' / f'{stem}.stl').is_file())
                printable = import_step(root / f'{stem}_print.step')
                self.assertAlmostEqual(printable.bounding_box().min.Z, 0.)
            exploded = import_step(root / viewer['exploded']['assembly'])
            exploded_parts = {child.label: child for child in exploded.children}
            self.assertLess(exploded_parts['gear'].bounding_box().max.Z,
                            exploded_parts['handle'].bounding_box().min.Z)
            instructions = (root / 'print-assembly.txt').read_text()
            self.assertIn('0.2 mm per side', instructions)
            self.assertIn('Disable supports', instructions)

    def test_overlapping_assembly_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict('sys.modules', {'vault.key': _key_module(overlap=True)}), \
                    patch('vault.render.render_review'):
                with self.assertRaisesRegex(ValueError, 'parts overlap'):
                    key_build._export_key(root, _Dimensions(), _Spec())
            self.assertFalse((root / 'snap_key_assembled.step').exists())

    def test_dimensions_are_saved_in_transaction_configuration(self):
        with patch.dict('sys.modules', {'vault.key': _key_module()}), \
                patch.object(key_build, 'run_build') as transaction:
            key_build.build_key(Path('/tmp/key-test-output'), _Dimensions(.25))
        configuration = transaction.call_args.kwargs['parameters']
        self.assertEqual(configuration['part'], 'snap_key')
        self.assertEqual(configuration['key_dimensions'], {'clearance': .25})
        self.assertEqual(transaction.call_args.kwargs['aliases'], ['latest/snap_key'])

    def test_disconnected_assembly_component_is_rejected(self):
        invalid = Compound(children=[Solid.make_box(2, 2, 2),
                                     Solid.make_box(2, 2, 2).translate((4, 0, 0))])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'one valid solid'):
                key_build._checked_assembly_export(
                    Path(directory), 'bad', {'gear': invalid}, name='Bad key')


if __name__ == '__main__':
    unittest.main()
