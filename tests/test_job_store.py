"""Queue transactions, dependency scheduling, migration and recovery."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from vault.generator import Configuration
from vault.job_store import JobStore


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / 'web'
        self.store = JobStore(self.state)

    def test_simultaneous_submission_deduplicates_across_connections(self):
        stores = [JobStore(self.state) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda store: store.submit(Configuration())['id'], stores))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(self.store.list()['total'], 1)
        with sqlite3.connect(self.store.path) as db:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)

    def test_simultaneous_capacity_is_global_and_dedup_still_works_when_full(self):
        configs = [Configuration(family=family, depth_units=depth, part='box')
                   for family in ('S', 'M') for depth in (3, 4, 5, 6)]
        def submit(config):
            try:
                return self.store.submit(config, capacity=4)
            except OverflowError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(submit, configs))
        accepted = [result for result in results if result]
        self.assertEqual(len(accepted), 4)
        self.assertEqual(self.store.list()['counts']['queued'], 4)
        existing = accepted[0]
        self.assertEqual(self.store.submit(Configuration.parse(existing['configuration']))['id'], existing['id'])

    def test_claim_is_atomic_and_assembly_waits_for_all_parts(self):
        job = self.store.submit(Configuration())
        with ThreadPoolExecutor(max_workers=12) as pool:
            claims = list(pool.map(lambda _: self.store.claim('revision-a'), range(12)))
        self.assertEqual(len({task['id'] for task in claims}), 12)
        self.assertNotIn('assembly', {task['kind'] for task in claims})
        self.assertIsNone(self.store.claim('revision-a'))
        for index, task in enumerate(claims):
            self.store.finish(task['id'], build_ids=[f'build-{task["kind"]}'])
            if index < 11:
                self.assertIsNone(self.store.claim('revision-a'))
        assembly = self.store.claim('revision-a')
        self.assertEqual(assembly['kind'], 'assembly')
        self.assertEqual(list(assembly['component_builds']), list(Configuration().parts))
        self.store.finish(assembly['id'], build_ids=list(assembly['component_builds'].values()))
        completed = self.store.get(job['id'])
        self.assertEqual(completed['status'], 'completed')
        self.assertEqual(len(completed['build_ids']), 12)
        self.assertIsNotNone(completed['elapsed_seconds'])

    def test_source_is_pinned_across_claims_and_change_fails_job(self):
        job = self.store.submit(Configuration())
        first = self.store.claim('revision-a')
        self.assertEqual(first['source_digest'], 'revision-a')
        self.assertIsNone(self.store.claim('revision-b'))
        updated = self.store.get(job['id'])
        self.assertEqual(updated['status'], 'failed')
        self.assertIn('source changed', updated['error'])
        self.assertIsNone(self.store.claim('revision-a'))

    def test_failure_preserves_completed_parts_and_blocks_assembly(self):
        job = self.store.submit(Configuration())
        first = self.store.claim('source')
        self.store.finish(first['id'], build_ids=['module-build'])
        failed = self.store.claim('source')
        self.store.finish(failed['id'], error='Bad shell')
        result = self.store.get(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['build_ids'], ['module-build'])
        self.assertEqual(next(task for task in result['tasks'] if task['kind'] == 'assembly')['status'], 'cancelled')
        self.assertIsNone(self.store.claim('source'))

    def test_failed_task_cancels_siblings_without_misattributing_its_error(self):
        job = self.store.submit(Configuration())
        module = self.store.claim('source')
        box = self.store.claim('source')
        facade = self.store.claim('source')
        self.store.finish(facade['id'], build_ids=['facade-build'])
        self.store.finish(box['id'], error='Box has an invalid shell')
        result = self.store.get(job['id'])
        tasks = {task['kind']: task for task in result['tasks']}
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error'], 'Box has an invalid shell')
        self.assertEqual(tasks['box']['status'], 'failed')
        self.assertEqual(tasks['box']['error'], 'Box has an invalid shell')
        cause = 'Stopped because another task failed: box: Box has an invalid shell'
        for kind in ('module', 'rails', 'assembly'):
            self.assertEqual(tasks[kind]['status'], 'cancelled')
            self.assertEqual(tasks[kind]['error'], cause)
        self.assertEqual(tasks['facade']['status'], 'completed')
        self.assertEqual(tasks['facade']['build_ids'], ['facade-build'])

        # Buffered output from a killed sibling must not replace its cause or
        # resurrect its active stage, but a published artifact remains useful.
        self.store.event(module['id'], {'event': 'stage_started', 'stage': 'render'})
        self.store.event(module['id'], {'event': 'task_failed', 'error': 'Late worker error'})
        self.store.event(module['id'], {'event': 'part_completed', 'build_id': 'module-build', 'reused': False})
        self.store.finish(module['id'], error='Late process exit', build_ids=['module-build'])
        self.store.event(facade['id'], {'event': 'part_completed', 'build_id': 'wrong-build', 'reused': False})
        self.store.finish(facade['id'], error='Stale completion', build_ids=['wrong-build'])
        final = self.store.get(job['id'])
        tasks = {task['kind']: task for task in final['tasks']}
        self.assertEqual(tasks['module']['status'], 'cancelled')
        self.assertEqual(tasks['module']['error'], cause)
        self.assertIsNone(tasks['module']['stage'])
        self.assertEqual(tasks['facade']['status'], 'completed')
        self.assertEqual(tasks['facade']['build_ids'], ['facade-build'])
        self.assertEqual(final['build_ids'], ['module-build', 'facade-build'])
        self.assertEqual(final['error'], 'Box has an invalid shell')

    def test_job_timeout_cancels_tasks_with_job_cause(self):
        job = self.store.submit(Configuration())
        self.store.claim('source')
        self.store.claim('source')
        self.store.fail(job['id'], 'Build exceeded its execution limit')
        result = self.store.get(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(all(task['status'] == 'cancelled' for task in result['tasks']))
        self.assertTrue(all(task['error'] == 'Stopped because the job failed: Build exceeded its execution limit'
                            for task in result['tasks']))

    def test_open_never_recovers_running_work_but_owner_recovery_does(self):
        running = self.store.submit(Configuration())
        queued = self.store.submit(Configuration(part='key'))
        task = self.store.claim('source')
        self.store.event(task['id'], {'event': 'part_completed', 'build_id': 'published', 'reused': False})
        reopened = JobStore(self.state)
        self.assertEqual(reopened.get(running['id'])['status'], 'running')
        self.assertEqual(reopened.get(queued['id'])['status'], 'queued')
        self.assertEqual(reopened.recover_interrupted(), 1)
        self.assertEqual(reopened.get(running['id'])['status'], 'failed')
        interrupted = next(item for item in reopened.get(running['id'])['tasks'] if item['id'] == task['id'])
        self.assertEqual(interrupted['status'], 'failed')
        self.assertEqual(interrupted['error'], 'The service stopped during this task.')
        self.assertEqual(reopened.get(running['id'])['build_ids'], ['published'])
        self.assertIsNone(reopened.get(running['id'])['elapsed_seconds'])
        self.assertEqual(reopened.get(queued['id'])['status'], 'queued')
        self.assertEqual(reopened.claim('new-source')['job_id'], queued['id'])

    def test_telemetry_tracks_rendering_separately_and_retains_failure(self):
        job = self.store.submit(Configuration(part='box'))
        task = self.store.claim('source')
        self.store.event(task['id'], {'event': 'stage_started', 'stage': 'render'})
        self.assertEqual(self.store.get(job['id'])['tasks'][0]['stage'], 'render')
        self.store.event(task['id'], {'event': 'stage_finished', 'stage': 'render', 'elapsed_seconds': 2.5})
        self.store.event(task['id'], {'event': 'stage_finished', 'stage': 'render', 'elapsed_seconds': 1.5})
        self.store.event(task['id'], {'event': 'task_failed', 'error': 'Broken geometry'})
        current = self.store.get(job['id'])['tasks'][0]
        self.assertEqual(current['render_seconds'], 4.)
        self.assertEqual(current['error'], 'Broken geometry')
        self.assertEqual(len(current['stage_timings']), 2)

    def test_filters_pagination_and_queue_positions(self):
        first = self.store.submit(Configuration(part='module', depth_units=3))
        second = self.store.submit(Configuration(part='module', depth_units=4))
        third = self.store.submit(Configuration(part='module', depth_units=5))
        self.assertEqual(self.store.get(second['id'])['queue_position'], 2)
        self.store.cancel(first['id'])
        self.assertEqual(self.store.get(second['id'])['queue_position'], 1)
        active = self.store.list(status='active', limit=1, offset=1)
        self.assertEqual(active['total'], 2)
        self.assertEqual(active['jobs'][0]['id'], third['id'])
        self.assertEqual(self.store.list(status='terminal')['jobs'][0]['id'], first['id'])
        with self.assertRaises(ValueError):
            self.store.list(status='invalid')

    def test_legacy_import_is_once_read_only_and_has_unknown_timings(self):
        state = Path(self.temporary.name) / 'legacy'
        state.mkdir()
        job_id = 'a' * 32
        job = {'id': job_id, 'configuration': Configuration(part='module').as_dict(),
               'status': 'completed', 'created_at': '2026-10-29T00:00:00+00:00',
               'build_ids': ['legacy-build'], 'logs': 'Historical log', 'error': None}
        path = state / (job_id + '.json')
        original = json.dumps(job).encode()
        path.write_bytes(original)
        receipt = state / (job_id + '.receipt')
        receipt.write_text('["legacy-build"]')
        store = JobStore(state)
        imported = store.get(job_id)
        self.assertIsNone(imported['elapsed_seconds'])
        self.assertIsNone(imported['tasks'][0]['render_seconds'])
        self.assertEqual(imported['build_ids'], ['legacy-build'])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(receipt.read_text(), '["legacy-build"]')
        JobStore(state)
        self.assertEqual(store.list()['total'], 1)

    def test_legacy_queued_work_survives_and_legacy_running_recovers_explicitly(self):
        state = Path(self.temporary.name) / 'legacy-active'
        state.mkdir()
        for index, status in enumerate(('running', 'queued')):
            job_id = str(index) * 32
            job = {'id': job_id, 'configuration': Configuration(part='module', depth_units=3 + index).as_dict(),
                   'status': status, 'created_at': f'2026-10-29T00:00:0{index}+00:00', 'logs': '', 'build_ids': []}
            (state / (job_id + '.json')).write_text(json.dumps(job))
        store = JobStore(state)
        self.assertEqual(store.get('0' * 32)['status'], 'running')
        store.recover_interrupted()
        self.assertEqual(store.get('0' * 32)['status'], 'failed')
        self.assertEqual(store.get('1' * 32)['status'], 'queued')
        self.assertEqual(store.claim('source')['job_id'], '1' * 32)


if __name__ == '__main__':
    unittest.main()
