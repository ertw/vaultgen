"""Exercise the scheduler with real isolated lightweight worker subprocesses."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from vault.generator import Configuration
from vault.web_builds import BuildFiles
from vault.web_jobs import Jobs


WORKER = r'''
import argparse, json, os, sys, time
from pathlib import Path
p=argparse.ArgumentParser()
for flag in ('configuration','output','receipt','task','job-id','source-digest','build-ids'):
    p.add_argument('--'+flag)
a=p.parse_args()
config=json.loads(a.configuration)
root=Path(a.output)
(root / (a.task+'-'+a.job_id+'.started')).write_text(str(os.getpid()))
print('VAULT_EVENT '+json.dumps({'event':'stage_started','stage':'render'}),flush=True)
time.sleep(float((root/'delay').read_text()) if (root/'delay').exists() else .06)
if (root/'fail').exists() and a.task==(root/'fail').read_text():
    print('VAULT_EVENT '+json.dumps({'event':'task_failed','error':'Deliberate task failure'}),flush=True)
    sys.exit(1)
print('VAULT_EVENT '+json.dumps({'event':'stage_finished','stage':'render','elapsed_seconds':.025}),flush=True)
if a.task=='assembly':
    builds=list(json.loads(a.build_ids).values())
    path=root/'web'/'assemblies'/(a.job_id+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'validation':{'passed':True}}))
else:
    builds=[a.job_id+'-'+a.task]
    print('VAULT_EVENT '+json.dumps({'event':'part_completed','build_id':builds[0],'reused':False}),flush=True)
Path(a.receipt).write_text(json.dumps(builds))
'''


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.script = self.root / 'worker.py'
        self.script.write_text(WORKER)
        original = subprocess.Popen
        self.real_popen = original
        def spawn(command, **kwargs):
            return original([sys.executable, '-u', str(self.script), *command[4:]], **kwargs)
        self.addCleanup(patch.stopall)
        patch('vault.web_jobs.subprocess.Popen', side_effect=spawn).start()
        patch.object(Jobs, '_source_digest', return_value='fixed-source').start()
        patch.object(BuildFiles, 'describe', side_effect=lambda build_id: {'id': build_id, 'parts': []}).start()
        self.services = []
        self.addCleanup(self.stop_services)

    def service(self, **kwargs):
        jobs = Jobs(self.root, **kwargs)
        self.services.append(jobs)
        return jobs

    def stop_services(self):
        for jobs in self.services:
            jobs.close()

    def wait(self, condition, timeout=8):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            result = condition()
            if result:
                return result
            time.sleep(.015)
        self.fail('Timed out waiting for queue state')

    def terminal(self, jobs, job_id):
        return self.wait(lambda: (job if (job := jobs.get(job_id))['status'] in ('completed','failed','cancelled') else None))

    def test_two_slots_run_parts_concurrently_and_assembly_only_after_parts(self):
        (self.root / 'delay').write_text('.12')
        jobs = self.service(workers=2)
        submitted = jobs.submit(Configuration())
        maximum = 0
        deadline = time.monotonic() + 8
        while True:
            self.assertLess(time.monotonic(), deadline, 'Queue did not finish')
            current = jobs.get(submitted['id'])
            running = sum(task['status'] == 'running' for task in current['tasks'])
            maximum = max(maximum, running)
            self.assertLessEqual(running, 2)
            assembly = next(task for task in current['tasks'] if task['kind'] == 'assembly')
            if assembly['status'] in ('running', 'completed'):
                self.assertTrue(all(task['status'] == 'completed' for task in current['tasks'] if task['kind'] != 'assembly'))
            if current['status'] in ('completed','failed'):
                break
            time.sleep(.015)
        self.assertEqual(current['status'], 'completed', current.get('error'))
        self.assertEqual(maximum, 2)
        self.assertEqual(len(current['builds']), 12)
        self.assertTrue(all(task['render_seconds'] == .025 for task in current['tasks']))
        self.assertTrue(all(task['elapsed_seconds'] > 0 for task in current['tasks']))

    def test_pool_limit_is_global_across_jobs_and_cancel_does_not_kill_other_job(self):
        (self.root / 'delay').write_text('5')
        jobs = self.service(workers=2)
        first = jobs.submit(Configuration(part='module', depth_units=3))
        second = jobs.submit(Configuration(part='module', depth_units=4))
        third = jobs.submit(Configuration(part='module', depth_units=5))
        self.wait(lambda: jobs.get(first['id'])['status']=='running' and jobs.get(second['id'])['status']=='running')
        self.assertEqual(jobs.get(third['id'])['status'], 'queued')
        self.assertEqual(jobs.cancel(first['id'])['status'], 'cancelled')
        self.wait(lambda: jobs.get(third['id'])['status']=='running')
        self.assertEqual(jobs.get(second['id'])['status'], 'running')
        jobs.cancel(second['id']); jobs.cancel(third['id'])
        self.wait(lambda: not jobs.processes)

    def test_timeout_spans_parts_and_preserves_published_successes(self):
        (self.root / 'delay').write_text('.18')
        jobs = self.service(workers=1, timeout=.6)
        submitted = jobs.submit(Configuration())
        result = self.terminal(jobs, submitted['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('execution limit', result['error'])
        self.assertGreater(len(result['builds']), 0)
        self.assertLess(len(result['builds']), 12)
        self.wait(lambda: not jobs.processes)
        self.assertEqual(next(task for task in jobs.get(submitted['id'])['tasks'] if task['kind']=='assembly')['status'], 'cancelled')

    def test_failure_is_visible_partial_outputs_remain_and_retry_is_new_job(self):
        (self.root / 'fail').write_text('box')
        jobs = self.service(workers=1)
        first = jobs.submit(Configuration())
        failed = self.terminal(jobs, first['id'])
        self.assertEqual(failed['status'], 'failed')
        self.assertIn('Deliberate task failure', failed['error'])
        self.assertEqual(len(failed['builds']), 1)
        (self.root / 'fail').unlink()
        retried = jobs.retry(first['id'])
        self.assertNotEqual(retried['id'], first['id'])
        self.assertEqual(retried['retry_of'], first['id'])
        self.assertEqual(self.terminal(jobs, retried['id'])['status'], 'completed')
        self.assertEqual(jobs.get(first['id'])['status'], 'failed')

    def test_only_one_scheduler_owns_output_but_store_only_open_is_safe(self):
        jobs = self.service()
        with self.assertRaisesRegex(RuntimeError, 'already owns'):
            Jobs(self.root)
        observer = self.service(start_worker=False)
        self.assertEqual(observer.summaries()['total'], 0)
        jobs.close()
        replacement = self.service()
        self.assertIsNotNone(replacement.owner)

    def test_recovery_kills_cancelled_orphan_and_restores_its_published_receipt(self):
        observer = self.service(start_worker=False)
        job = observer.submit(Configuration(part='module'))
        task = observer.store.claim('fixed-source')
        process = self.real_popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        observer.store.process_started(task['id'], process.pid, Jobs._process_start(process.pid))
        observer.store.cancel(job['id'])
        receipt = observer._receipt(task)
        receipt.parent.mkdir(parents=True)
        receipt.write_text('["published-before-crash"]')
        recovered = self.service()
        process.wait(timeout=3)
        result = recovered.get(job['id'])
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['builds'][0]['id'], 'published-before-crash')
        self.assertEqual(recovered.store.running_processes(), [])

    def test_shutdown_preserves_queued_jobs_and_restart_runs_them(self):
        (self.root / 'delay').write_text('5')
        jobs = self.service(workers=1)
        first = jobs.submit(Configuration(part='module', depth_units=3))
        second = jobs.submit(Configuration(part='module', depth_units=4))
        self.wait(lambda: jobs.get(first['id'])['status']=='running')
        jobs.close()
        self.assertEqual(jobs.get(first['id'])['status'], 'failed')
        self.assertEqual(jobs.get(second['id'])['status'], 'queued')
        self.assertFalse(any(thread.is_alive() for thread in jobs.threads))
        (self.root / 'delay').write_text('.01')
        restarted = self.service(workers=1)
        self.assertEqual(self.terminal(restarted, second['id'])['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
