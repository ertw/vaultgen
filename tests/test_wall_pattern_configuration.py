"""Pattern requests retain their identities through selection and publication."""
from contextlib import redirect_stderr
from dataclasses import replace
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from vault import __main__ as cli
from vault.assembly import assembly_definition, build_finished_components
from vault.assembly_validation import validation_signature
from vault.generator import Configuration, catalog
from vault.spec import ModuleSpec, PATTERN_DEFAULTS, pattern_parameters


class PatternConfigurationTests(unittest.TestCase):
    def test_legacy_plain_identity_and_default_nozzle_target(self):
        plain = ModuleSpec()
        self.assertEqual(plain.slug, 's4_module_1f')
        self.assertEqual(plain.name, 'S4 Module 1F')
        self.assertEqual(ModuleSpec(wall_pattern='waffle').slug, 's4_module_1f_waffle')
        self.assertEqual(ModuleSpec(wall_pattern='miura').slug, 's4_module_1f_miura')
        self.assertEqual(ModuleSpec(wall_pattern='miura', pattern_construction='corrugated').slug,
                         's4_module_1f_miura_corrugated')
        self.assertAlmostEqual(3 - plain.pattern_depth, 2 * plain.pattern_line_width)
        self.assertEqual(ModuleSpec(pattern_pitch=20), plain)
        self.assertEqual(ModuleSpec(pattern_construction='corrugated'), plain)
        self.assertEqual(pattern_parameters(Configuration.parse({})), dict(PATTERN_DEFAULTS))
        self.assertEqual([item['id'] for item in catalog()['wall_patterns']], ['plain', 'waffle', 'miura'])
        self.assertEqual([item['id'] for item in catalog()['pattern_constructions']], ['recessed', 'corrugated'])

    def test_native_and_http_reject_invalid_or_under_thickness_parameters(self):
        values = [{'wall_pattern': 'honeycomb'}, {'wall_pattern': []}, {'pattern_faces': 'front'},
                  {'pattern_construction': 'solid'}, {'pattern_construction': []},
                  {'pattern_pitch': 7.9}, {'pattern_pitch': 40.1}, {'pattern_pitch': True},
                  {'pattern_pitch': float('nan')}, {'pattern_pitch': float('inf')},
                  {'pattern_pitch': '14'}, {'pattern_depth': .1}, {'pattern_depth': 2.1},
                  {'pattern_line_width': .59}, {'pattern_line_width': 1.1},
                  {'pattern_depth': 2}, {'pattern_depth': 1.5, 'pattern_line_width': .8}]
        for request in values:
            for constructor in (ModuleSpec, Configuration):
                with self.subTest(request=request, constructor=constructor.__name__), self.assertRaises(ValueError):
                    constructor(**request)

    def test_parameter_variants_have_stable_distinct_module_identities(self):
        base = ModuleSpec(wall_pattern='miura')
        variants = [base, replace(base, pattern_pitch=20), replace(base, pattern_depth=1.4),
                    replace(base, pattern_depth=1.4, pattern_line_width=.8),
                    replace(base, pattern_faces='sides'), replace(base, pattern_construction='corrugated')]
        self.assertEqual(len({spec.slug for spec in variants}), len(variants))
        self.assertEqual(replace(base, pattern_pitch=20).slug, replace(base, pattern_pitch=20.).slug)
        for kind in ('box', 'facade', 'rails', 'runner_guides', 'runner_slides', 'key'):
            self.assertEqual(cli.select_spec(kind, wall_pattern='waffle'), cli.select_spec(kind))
            self.assertEqual(cli.select_spec(kind, wall_pattern='waffle', pattern_construction='corrugated'),
                             cli.select_spec(kind))

    def test_cli_propagates_parameters_and_rejects_invalid_values_before_build(self):
        argv = ['vault', 'build', '--wall-pattern', 'miura', '--pattern-pitch', '20',
                '--pattern-depth', '1.4', '--pattern-line-width', '.8', '--pattern-faces', 'sides',
                '--pattern-construction', 'corrugated']
        with patch('sys.argv', argv), patch.object(cli, 'build') as build:
            cli.main()
        spec = build.call_args.args[1]
        self.assertEqual(pattern_parameters(spec), dict(wall_pattern='miura', pattern_pitch=20.,
                         pattern_depth=1.4, pattern_line_width=.8, pattern_faces='sides', pattern_construction='corrugated'))
        with patch('sys.argv', ['vault', 'build', '--wall-pattern', 'waffle', '--pattern-depth', '2']), \
                patch.object(cli, 'build') as build, redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            cli.main()
        build.assert_not_called()

    def test_publication_records_custom_pattern_and_preserves_shared_module_rows(self):
        spec = ModuleSpec('L', 6, 2, drawer_columns=2, drawer_rows=2,
                          wall_pattern='miura', pattern_pitch=20, pattern_construction='corrugated')
        with patch.object(cli, 'run_build') as transaction:
            cli.build(Path('/tmp/pattern-publication-test'), spec)
        parameters = transaction.call_args.kwargs['parameters']
        self.assertEqual(parameters['wall_pattern'], 'miura')
        self.assertEqual(parameters['pattern_construction'], 'corrugated')
        self.assertEqual(parameters['pattern_pitch'], 20.)
        self.assertEqual(parameters['drawer_rows'], 1)
        self.assertEqual(parameters['part'], spec.slug)

    def test_finished_module_and_receipt_include_pattern_without_moving_components(self):
        config = Configuration(wall_pattern='miura', pattern_pitch=20, pattern_construction='corrugated')
        plain_scene, scene = assembly_definition(Configuration()), assembly_definition(config)
        self.assertEqual([item['transform'] for item in plain_scene['instances']],
                         [item['transform'] for item in scene['instances']])
        self.assertIn('Miura-ori', scene['instances'][0]['label'])
        self.assertNotEqual(validation_signature(Configuration()), validation_signature(config))
        self.assertNotEqual(validation_signature(config), validation_signature(replace(config, pattern_pitch=21)))
        self.assertNotEqual(validation_signature(config), validation_signature(replace(config, pattern_construction='recessed')))
        self.assertEqual(validation_signature(config), validation_signature(replace(config, pattern_pitch=20.)))
        with patch('vault.model.build_module') as module, patch('vault.box.build_box'), \
                patch('vault.facade.build_facade'), patch('vault.geared_rails.build_gear_rail'), \
                patch('vault.runner_guides.build_runner_guide'), patch('vault.runner_slides.build_runner_slide'):
            build_finished_components(config)
        self.assertFalse(module.call_args.kwargs['include_supports'])
        self.assertEqual(pattern_parameters(module.call_args.kwargs['spec']), pattern_parameters(config))


if __name__ == '__main__':
    unittest.main()
