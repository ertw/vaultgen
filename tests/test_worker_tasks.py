"""Isolated queue tasks preserve provenance, failures, and timing evidence."""
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from vault import assembly_validation, build as build_api
from vault._build import source_digest
from vault.build_events import PREFIX, event_output, stage
from vault.generator import Configuration, ASSEMBLY_PARTS
from vault.web_worker import main


class WorkerTaskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.config = Configuration()
        self.sources = {'worker.py': 'current-source'}
        self.digest = source_digest(self.sources)
        self.receipt = self.output / 'task.receipt'
        self.job_id = 'a' * 32
        self.stdout = io.StringIO()

    def invoke(self, task, *, build_ids=None, digest=None, build=None, sources=None, validator=None):
        argv = ['--configuration', json.dumps(self.config.as_dict()),
                '--output', str(self.output), '--receipt', str(self.receipt),
                '--task', task, '--job-id', self.job_id,
                '--source-digest', self.digest if digest is None else digest]
        if build_ids is not None:
            argv += ['--build-ids', json.dumps(build_ids)]
        self.build = Mock(side_effect=build) if build else Mock(return_value=self.output / 'builds' / 'new-build')
        self.validate = Mock(return_value=validator or {'passed': True, 'pairs': []})
        self.import_step = Mock(side_effect=lambda path: ('finished-step', Path(path)))
        with ExitStack() as stack:
            stack.enter_context(patch('vault._build.source_hashes', side_effect=sources,
                                      return_value=self.sources))
            stack.enter_context(patch.object(build_api, 'build', self.build))
            stack.enter_context(patch.object(build_api, 'select_spec', side_effect=lambda kind, *a, **k:
                                            SimpleNamespace(kind=kind, slug=kind, name=kind)))
            stack.enter_context(patch.dict(sys.modules, {'build123d': SimpleNamespace(import_step=self.import_step)}))
            stack.enter_context(patch.object(assembly_validation, 'validate_assembly', self.validate))
            stack.enter_context(redirect_stdout(self.stdout))
            main(argv)

    def events(self):
        return [json.loads(line[len(PREFIX):]) for line in self.stdout.getvalue().splitlines()
                if line.startswith(PREFIX)]

    def components(self):
        builds = {}
        for index, kind in enumerate(self.config.parts):
            build_id = f'20261030T010000{index:06d}Z-0123456789ab'
            builds[kind] = build_id
            directory = self.output / 'builds' / build_id
            directory.mkdir(parents=True)
            relative = 'preview/assembly/finished.step'
            step = directory / relative
            step.parent.mkdir(parents=True)
            step.write_bytes(kind.encode())
            (directory / 'manifest.json').write_text(json.dumps({
                'passed': True, 'build_id': build_id, 'source_hash': self.digest,
                'checksums': {relative: hashlib.sha256(step.read_bytes()).hexdigest()},
                'parts': {'single': {'assembly_mesh': {
                    'schema': 'vault-assembly-mesh/v1', 'finished': True,
                    'coordinates': 'native', 'component': 'single', 'step_path': relative}}},
            }))
        return builds

    def test_one_part_task_of_set_only_builds_requested_group_and_writes_atomic_receipt(self):
        self.invoke('box')
        self.build.assert_called_once()
        self.assertEqual(self.build.call_args.args[1].kind, 'box')
        self.assertEqual(json.loads(self.receipt.read_text()), ['new-build'])
        self.assertFalse(self.receipt.with_name('task.receipt.tmp').exists())
        self.validate.assert_not_called()
        completed = next(event for event in self.events() if event['event'] == 'part_completed')
        self.assertEqual((completed['part'], completed['build_id'], completed['reused']),
                         ('box', 'new-build', False))

    def test_pinned_source_is_checked_before_any_build(self):
        with self.assertRaisesRegex(RuntimeError, 'source changed since this job started'):
            self.invoke('box', digest='different-source')
        self.build.assert_not_called()
        self.assertFalse(self.receipt.exists())
        failure = self.events()[-1]
        self.assertEqual(failure['event'], 'task_failed')
        self.assertIn('source changed', failure['error'])

    def test_failed_construction_reports_actual_error_and_stage_duration(self):
        def fail(*args):
            with stage('construction'):
                raise ValueError('Runner fillet could not be constructed')
        with self.assertRaisesRegex(ValueError, 'Runner fillet'):
            self.invoke('box', build=fail)
        event = next(event for event in self.events()
                     if event['event'] == 'stage_finished' and event['stage'] == 'construction')
        self.assertTrue(event['failed'])
        self.assertGreaterEqual(event['elapsed_seconds'], 0)
        failure = self.events()[-1]
        self.assertEqual(failure['error'], 'ValueError: Runner fillet could not be constructed')
        self.assertIn('Traceback', failure['traceback'])
        self.assertFalse(self.receipt.exists())

    def test_late_source_change_fails_but_preserves_checked_partial_result(self):
        with self.assertRaisesRegex(RuntimeError, 'source changed during this set'):
            self.invoke('box', sources=[self.sources, self.sources, {'worker.py': 'new-code'}])
        self.assertEqual(json.loads(self.receipt.read_text()), ['new-build'])
        self.assertEqual(self.events()[-1]['event'], 'task_failed')

    def test_assembly_task_uses_all_exact_finished_components_and_parent_receipt(self):
        builds = self.components()
        self.invoke('assembly', build_ids=builds)
        self.build.assert_not_called()
        self.validate.assert_called_once()
        self.assertEqual(set(self.validate.call_args.kwargs['components']),
                         {(kind, 'single') for kind in ASSEMBLY_PARTS})
        self.assertEqual(self.import_step.call_count, len(ASSEMBLY_PARTS))
        self.assertEqual(json.loads(self.receipt.read_text()), list(builds.values()))
        receipt = json.loads((self.output / 'web' / 'assemblies' / f'{self.job_id}.json').read_text())
        self.assertEqual(receipt['build_ids'], [builds[kind] for kind in self.config.parts if kind in ASSEMBLY_PARTS])
        self.assertEqual(set(receipt['accessory_build_ids']),
                         {builds[kind] for kind in self.config.parts if kind not in ASSEMBLY_PARTS})
        phases = {event['stage'] for event in self.events() if event['event'] == 'stage_finished'}
        self.assertEqual(phases, {'assembly_import', 'assembly_validation'})

    def test_assembly_rejects_component_from_other_source_including_accessories(self):
        builds = self.components()
        manifest_path = self.output / 'builds' / builds['latch'] / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['source_hash'] = 'older-source'
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RuntimeError, 'do not share'):
            self.invoke('assembly', build_ids=builds)
        self.validate.assert_not_called()
        self.assertFalse((self.output / 'web' / 'assemblies').exists())

    def test_failed_assembly_preserves_audit_and_reports_exception(self):
        builds = self.components()
        report = {'passed': False, 'pairs': [{'instances': ['box', 'module'], 'passed': False}]}
        with self.assertRaisesRegex(RuntimeError, 'Assembly fit checks failed'):
            self.invoke('assembly', build_ids=builds, validator=report)
        receipt = json.loads((self.output / 'web' / 'assemblies' / f'{self.job_id}.json').read_text())
        self.assertEqual(receipt['validation'], report)
        self.assertFalse(self.receipt.exists())
        self.assertIn('Assembly fit checks failed', self.events()[-1]['error'])

    def test_assembly_requires_complete_mapping_and_rejects_traversal(self):
        with self.assertRaisesRegex(ValueError, 'exactly one checked build ID'):
            self.invoke('assembly', build_ids={'module': 'partial'})
        builds = self.components()
        builds['module'] = '../elsewhere'
        with self.assertRaisesRegex(ValueError, 'Invalid component build ID'):
            self.invoke('assembly', build_ids=builds)
        self.import_step.assert_not_called()


class TimingEventTests(unittest.TestCase):
    def test_nested_phases_and_failures_keep_wall_time_without_hiding_exception(self):
        output = io.StringIO()
        with patch.dict('os.environ', {}, clear=True), redirect_stdout(output), event_output(), \
                patch('vault.build_events.time.monotonic', side_effect=[10, 12, 13, 18]):
            with self.assertRaisesRegex(ValueError, 'bad mesh'):
                with stage('exports'):
                    with stage('render'):
                        raise ValueError('bad mesh')
        events = [json.loads(line[len(PREFIX):]) for line in output.getvalue().splitlines()]
        finished = [event for event in events if event['event'] == 'stage_finished']
        self.assertEqual([(event['stage'], event['elapsed_seconds']) for event in finished],
                         [('render', 1), ('exports', 8)])
        self.assertTrue(all(event['failed'] for event in finished))

    def test_render_phase_covers_actual_review_renderer(self):
        from vault.render import render_review
        output = io.StringIO()
        with redirect_stdout(output), event_output(), patch('vault.render.render_mesh') as render:
            render_review(None, Path('/unused'))
        self.assertEqual(render.call_count, 4)
        events = [json.loads(line[len(PREFIX):]) for line in output.getvalue().splitlines()]
        self.assertEqual([event['event'] for event in events], ['stage_started', 'stage_finished'])
        self.assertEqual(events[-1]['stage'], 'render')
        self.assertGreaterEqual(events[-1]['elapsed_seconds'], 0)
        self.assertFalse(events[-1]['failed'])

    def test_normal_cli_output_is_unchanged_when_events_are_disabled(self):
        output = io.StringIO()
        with patch.dict('os.environ', {}, clear=True), redirect_stdout(output), event_output(False):
            with stage('construction'):
                pass
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
