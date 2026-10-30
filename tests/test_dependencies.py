"""Behavioral checks for conservative dependency invalidation."""
import json
from pathlib import Path
import tempfile
import unittest

from vault.dependencies import dependency_graph, fingerprint, fingerprint_digest, kind_for_parameters
from vault.project import PROJECT_ROOT


class DependencyGraphTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'cad' / 'projects' / 'vault'
        self.root.mkdir(parents=True)
        self.write('src/vault/__init__.py', '')
        self.write('src/vault/dependencies.py', '# fingerprint policy\n')
        self.write('src/vault/key_build.py', 'from .key import build_key\n')
        self.write('src/vault/key.py', 'def build_key():\n    from .key_geometry import blank\n    return blank()\n')
        self.write('src/vault/key_geometry.py', 'def blank(): return 1\n')
        self.write('src/vault/box.py', '# unrelated box geometry\n')
        for name in ('pyproject.toml', 'uv.lock', 'flake.nix', 'flake.lock'):
            self.write(name, '# pinned environment\n')
        tooling = self.root.parents[1] / 'cad-tooling/src/cad_build'
        tooling.mkdir(parents=True)
        (tooling / '__init__.py').write_text('# shared storage\n')
        self.toolchain = {'python': 'fixture', 'packages': [['build123d', 'fixture']]}

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def key(self, **kwargs):
        return fingerprint('key', kwargs.get('parameters', {'part': 'snap_key'}),
                           root=self.root, toolchain=kwargs.get('toolchain', self.toolchain))

    def test_function_local_imports_and_package_initializers_are_dependencies(self):
        record = self.key()
        self.assertTrue(record['reusable'], record['reasons'])
        self.assertIn('src/vault/key_geometry.py', record['source_files'])
        self.assertIn('src/vault/__init__.py', record['source_files'])
        self.assertIn('src/vault/key_geometry.py', record['edges']['src/vault/key.py'])
        self.write('src/vault/key_geometry.py', 'def blank(): return 2\n')
        self.assertNotEqual(record['digest'], self.key()['digest'])

    def test_unrelated_geometry_browser_and_tests_do_not_invalidate_key(self):
        before = self.key()
        self.write('src/vault/box.py', '# changed box\n')
        self.write('src/vault/static/app.css', 'body { color: red; }')
        self.write('tests/test_key.py', '# a test change\n')
        self.assertEqual(before, self.key())

    def test_resolved_parameters_and_actual_environment_invalidate(self):
        before = self.key()['digest']
        self.assertNotEqual(before, self.key(parameters={'part': 'snap_key', 'clearance': .1})['digest'])
        self.assertNotEqual(before, self.key(toolchain={'python': 'different'})['digest'])

    def test_equivalent_numeric_parameters_share_fingerprint(self):
        first = self.key(parameters={'floor': 3.0, 'nested': [{'height': 2.0}], 'enabled': True})
        second = self.key(parameters={'floor': 3, 'nested': [{'height': 2}], 'enabled': True})
        self.assertEqual(first, second)
        self.assertIs(first['parameters']['enabled'], True)
        self.assertNotEqual(first['digest'], self.key(parameters={
            'floor': 3, 'nested': [{'height': 2}], 'enabled': 1})['digest'])

    def test_export_helper_and_shared_storage_invalidate(self):
        self.write('src/vault/key_build.py', 'from .key import build_key\nfrom .exports import export\n')
        self.write('src/vault/exports.py', 'def export(): return True\n')
        before = self.key()['digest']
        self.write('src/vault/exports.py', 'def export(): return False\n')
        self.assertNotEqual(before, self.key()['digest'])
        before = self.key()['digest']
        shared = self.root.parents[1] / 'cad-tooling/src/cad_build/__init__.py'
        shared.write_text('# modified shared storage\n')
        self.assertNotEqual(before, self.key()['digest'])

    def test_declared_font_and_renderer_assets_follow_import_graph(self):
        self.write('src/vault/key_build.py', 'from . import native_renderer\n')
        self.write('src/vault/native_renderer.py', '# renderer\n')
        self.write('src/vault/rasterizer.c', 'int render(void) { return 1; }')
        first = self.key()
        self.assertIn('src/vault/rasterizer.c', first['source_files'])
        self.write('src/vault/rasterizer.c', 'int render(void) { return 2; }')
        self.assertNotEqual(first['digest'], self.key()['digest'])
        self.write('src/vault/label_build.py', 'from . import label_config\n')
        self.write('src/vault/label_config.py', '# font consumer\n')
        self.write('src/vault/static/label-font.json', '{"outlines":1}')
        first = fingerprint('label', {}, root=self.root, toolchain=self.toolchain)
        self.write('src/vault/static/label-font.json', '{"outlines":2}')
        self.assertNotEqual(first['digest'], fingerprint('label', {}, root=self.root,
                                                       toolchain=self.toolchain)['digest'])

    def test_missing_asset_or_local_import_fails_closed(self):
        self.write('src/vault/key_build.py', 'from . import native_renderer\nfrom .missing import feature\n')
        self.write('src/vault/native_renderer.py', '# renderer\n')
        record = self.key()
        self.assertFalse(record['reusable'])
        self.assertTrue(any('rasterizer.c' in reason for reason in record['reasons']))
        self.assertTrue(any('vault.missing' in reason for reason in record['reasons']))

    def test_dynamic_loading_and_syntax_errors_fail_closed(self):
        for content in ('from importlib import import_module as load\nload("vault.key")\n',
                        'import importlib\nimportlib.import_module("vault.key")\n',
                        'def call(): load("vault.key")\nfrom importlib import import_module as load\n',
                        '__import__("vault.key")\n', 'def broken(:\n'):
            with self.subTest(content=content):
                self.write('src/vault/key_build.py', content)
                self.assertFalse(self.key()['reusable'])

    def test_missing_package_exports_fail_closed(self):
        self.write('src/vault/key_build.py', 'from . import missing\n')
        record = self.key()
        self.assertFalse(record['reusable'])
        self.assertTrue(any('vault.missing' in reason for reason in record['reasons']))

    def test_other_source_packages_and_top_level_helpers_are_followed(self):
        self.write('src/vault/key_build.py', 'import helper\nfrom local_features import geometry\n')
        self.write('src/helper.py', 'from local_features.geometry import shape\n')
        self.write('src/local_features/__init__.py', '')
        self.write('src/local_features/geometry.py', 'shape = 1\n')
        record = self.key()
        self.assertTrue(record['reusable'], record['reasons'])
        for name in ('src/helper.py', 'src/local_features/__init__.py', 'src/local_features/geometry.py'):
            self.assertIn(name, record['source_files'])

    def test_changed_import_adds_dependency_and_cycles_terminate(self):
        before = self.key()
        self.write('src/vault/key_geometry.py', 'from . import key\nfrom .box import thing\n')
        after = self.key()
        self.assertTrue(after['reusable'], after['reasons'])
        self.assertNotEqual(before['digest'], after['digest'])
        self.assertIn('src/vault/box.py', after['source_files'])

    def test_lockfile_and_policy_changes_invalidate(self):
        before = self.key()['digest']
        self.write('uv.lock', '# updated lock\n')
        self.assertNotEqual(before, self.key()['digest'])
        before = self.key()['digest']
        self.write('src/vault/dependencies.py', '# updated policy\n')
        self.assertNotEqual(before, self.key()['digest'])

    def test_fingerprint_roundtrips_and_unknown_kind_cannot_reuse(self):
        record = self.key(toolchain={'versions': [('package', 'version')]})
        self.assertEqual(record, json.loads(json.dumps(record)))
        self.assertEqual(record['digest'], fingerprint_digest(record))
        self.assertNotEqual(record['digest'], fingerprint_digest({**record, 'kind': 'box'}))
        self.assertFalse(fingerprint('unknown', {}, root=self.root,
                                     toolchain=self.toolchain)['reusable'])
        self.assertFalse(self.key(toolchain={'compiler_error': 'unavailable'})['reusable'])

    def test_parameter_kind_recognition(self):
        for parameters, kind in (({'part': 'snap_key'}, 'key'),
                                 ({'part': 's1f_facade'}, 'facade'),
                                 ({'part': 's1f_facade_floor_0p8'}, 'facade'),
                                 ({'part': 's4_box_1f'}, 'box'),
                                 ({'part': 's4_module_1f'}, 'module'),
                                 ({'part': 's_geared_rails'}, 'rails'),
                                 ({'part': 'x4_runner_guides'}, 'runner_guides'),
                                 ({'part': 'spring'}, 'spring'),
                                 ({'label_configuration': {}}, 'label'),
                                 ({'gridfinity_configuration': {}}, 'gridfinity_bins')):
            self.assertEqual(kind_for_parameters(parameters), kind)
        self.assertIsNone(kind_for_parameters({'part': 'unknown'}))

    def test_real_key_graph_excludes_box_and_includes_exports(self):
        record = dependency_graph('key', root=PROJECT_ROOT)
        self.assertTrue(record['reusable'], record['reasons'])
        self.assertIn('src/vault/key_geometry.py', record['source_files'])
        self.assertIn('src/vault/exports.py', record['source_files'])
        self.assertIn('src/vault/rasterizer.c', record['source_files'])
        self.assertNotIn('src/vault/box.py', record['source_files'])
        self.assertNotIn('src/vault/static/app.js', record['source_files'])


if __name__ == '__main__':
    unittest.main()
