"""Persistent task queue and bounded pool of isolated CAD subprocesses."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

from .generator import parse_configuration
from .job_store import ACTIVE, TERMINAL, JOB_ID, JobStore, now, seconds
from .project import PROJECT_ROOT
from .web_builds import BuildFiles


class Jobs:
    def __init__(self, output, *, start_worker=True, timeout=3600, workers=2, capacity=4):
        if type(workers) is not int or not 1 <= workers <= 4:
            raise ValueError('workers must be an integer from 1 to 4')
        if type(capacity) is not int or not 1 <= capacity <= 100:
            raise ValueError('capacity must be an integer from 1 to 100')
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        self.output = Path(output).resolve()
        self.state = self.output / 'web'
        self.state.mkdir(parents=True, exist_ok=True)
        self.files = BuildFiles(output)
        self.timeout, self.workers, self.capacity = timeout, workers, capacity
        self.lock = threading.RLock()
        self.wake = threading.Condition(self.lock)
        self.stopping = False
        self.processes = {}
        self.threads = []
        self.owner = None
        try:
            if start_worker:
                self.owner = (self.state / 'scheduler.lock').open('a+')
                try:
                    fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('A CAD scheduler already owns this output directory') from None
            self.store = JobStore(self.state)
            if start_worker:
                self._recover()
                for index in range(workers):
                    thread = threading.Thread(target=self._work, name=f'vault-build-{index + 1}', daemon=True)
                    self.threads.append(thread)
                    thread.start()
                thread = threading.Thread(target=self._monitor, name='vault-queue-monitor', daemon=True)
                self.threads.append(thread)
                thread.start()
        except BaseException:
            if self.owner is not None:
                self.owner.close()
                self.owner = None
            raise

    def describe(self, item):
        builds = []
        for build_id in item.get('build_ids', []):
            try:
                builds.append(self.files.describe(build_id))
            except (OSError, ValueError, KeyError):
                pass
        return {key: value for key, value in item.items() if key != 'build_ids'} | {
            'builds': builds,
            'bundle_url': f'/api/jobs/{item["id"]}/bundle.zip' if item['status'] == 'completed' else None}

    def get(self, job_id):
        return self.describe(self.store.get(job_id))

    def history(self):
        return [self.get(item['id']) for item in self.store.list(active_first=False)['jobs']]

    def summaries(self, *, status=None, limit=30, offset=0):
        result = self.store.list(status=status, limit=limit, offset=offset)
        result['jobs'] = [{key: value for key, value in item.items()
                           if key not in ('logs', 'build_ids', 'source_digest')}
                          for item in result['jobs']]
        return {**result, 'workers': self.workers, 'capacity': self.capacity}

    def submit(self, config):
        with self.wake:
            if self.stopping:
                raise RuntimeError('The build service is stopping')
            item = self.store.submit(config, capacity=self.capacity)
            self.wake.notify_all()
        return self.get(item['id'])

    def cancel(self, job_id):
        # Spawn and registry writes hold this same lock: cancellation cannot miss
        # a newly started process between claiming a task and registering its PID.
        with self.wake:
            self.store.cancel(job_id)
            self._stop_job(job_id)
            self.wake.notify_all()
        return self.get(job_id)

    def retry(self, job_id):
        with self.wake:
            if self.stopping:
                raise RuntimeError('The build service is stopping')
            previous = self.store.get(job_id)
            if previous['status'] not in TERMINAL:
                raise ValueError('Only a finished job can be retried')
            config = parse_configuration(previous['configuration'])
            item = self.store.submit(config, capacity=self.capacity, retry_of=job_id)
            self.wake.notify_all()
        return self.get(item['id'])

    @staticmethod
    def _source_digest():
        from ._build import source_hashes, source_digest
        return source_digest(source_hashes(PROJECT_ROOT))

    @staticmethod
    def _process_start(pid):
        """Linux process start tick prevents killing an unrelated reused PID."""
        try:
            text = Path(f'/proc/{pid}/stat').read_text()
            start = text[text.rfind(')') + 2:].split()[19]
            boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            return f'{boot}:{start}'
        except (OSError, IndexError):
            return None

    def _receipt(self, task):
        return self.state / 'tasks' / (task['id'] + '.receipt')

    def _receipt_builds(self, task):
        path = self._receipt(task)
        if not path.is_file():
            return []
        builds = json.loads(path.read_text())
        if not isinstance(builds, list) or any(not isinstance(item, str) for item in builds):
            raise ValueError('CAD worker published an invalid receipt')
        for build_id in builds:
            self.files.describe(build_id)
        return builds

    def _recover(self):
        for task in self.store.running_processes():
            pid, expected = task.get('pid'), task.get('process_start')
            if pid and expected and self._process_start(pid) == expected:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                builds = self._receipt_builds(task)
                for build_id in builds:
                    if task['kind'] != 'assembly':
                        self.store.event(task['id'], {'event': 'part_completed', 'build_id': build_id,
                                                      'reused': task.get('reused', False)})
            except (OSError, ValueError, KeyError):
                pass
            self.store.clear_process(task['id'])
        self.store.recover_interrupted()

    def _work(self):
        while True:
            with self.wake:
                if self.stopping:
                    return
                if not self.store.has_ready():
                    self.wake.wait(timeout=.5)
                    continue
            # Hash outside the transaction. Every actual worker independently
            # checks the pinned digest again, including before publication.
            try:
                digest = self._source_digest()
                with self.wake:
                    if self.stopping:
                        return
                    task = self.store.claim(digest)
                    if task is None:
                        self.wake.wait(timeout=.5)
                        continue
                self._execute(task)
            except Exception:
                # An infrastructure error must not silently remove a pool slot.
                # Claimed work is failed by _execute; other errors are retried.
                with self.wake:
                    if not self.stopping:
                        self.wake.wait(timeout=1.)

    def _execute(self, task):
        receipt = self._receipt(task)
        process, error, builds = None, None, []
        try:
            receipt.parent.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, '-u', '-m', 'vault.web_worker',
                       '--configuration', json.dumps(task['configuration']),
                       '--output', str(self.output), '--receipt', str(receipt),
                       '--task', task['kind'], '--job-id', task['job_id'],
                       '--source-digest', task['source_digest']]
            if task['kind'] == 'assembly':
                command += ['--build-ids', json.dumps(task['component_builds'])]
            with self.wake:
                if self.stopping:
                    raise RuntimeError('The service stopped during this task; completed parts remain available.')
                if self.store.get(task['job_id'])['status'] not in ACTIVE:
                    return
                process = subprocess.Popen(command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, start_new_session=True)
                self.processes[task['id']] = (task['job_id'], process)
                valid = self.store.process_started(task['id'], process.pid, self._process_start(process.pid))
                if not valid:
                    self._terminate(process)
            worker_error = None
            for line in process.stdout:
                if line.startswith('VAULT_EVENT '):
                    try:
                        event = json.loads(line.removeprefix('VAULT_EVENT '))
                        if not isinstance(event, dict):
                            raise ValueError('Invalid worker event')
                        self.store.event(task['id'], event)
                        if event.get('event') == 'task_failed':
                            worker_error = str(event.get('error', 'CAD task failed'))
                        continue
                    except (ValueError, TypeError, KeyError):
                        pass
                self.store.log(task['id'], line)
            code = process.wait()
            if code:
                job = self.store.get(task['job_id'])
                raise RuntimeError(job['error'] or worker_error or
                                   ('The service stopped during this task.' if self.stopping else '') or
                                   'CAD generation failed. See the task log; completed parts remain available.')
            builds = self._receipt_builds(task)
            expected = list(task['component_builds'].values()) if task['kind'] == 'assembly' else None
            if task['kind'] == 'assembly':
                if builds != expected:
                    raise RuntimeError('Assembly worker did not return the exact component builds')
                assembly = self.state / 'assemblies' / (task['job_id'] + '.json')
                record = json.loads(assembly.read_text())
                if record.get('validation', {}).get('passed') is not True:
                    raise RuntimeError('Assembly worker did not publish a passing fit receipt')
            elif len(builds) != 1:
                raise RuntimeError('CAD worker did not publish exactly one checked build')
        except Exception as exception:
            error = str(exception)
        finally:
            if process is not None:
                self._terminate(process)
                process.wait()
                if process.stdout is not None:
                    process.stdout.close()
            if not builds:
                try:
                    builds = self._receipt_builds(task)
                except (OSError, ValueError, KeyError):
                    pass
            with self.wake:
                self.processes.pop(task['id'], None)
                job = self.store.finish(task['id'], error=error, build_ids=builds)
                if job['status'] in TERMINAL:
                    self._stop_job(job['id'])
                self.wake.notify_all()

    def _monitor(self):
        while True:
            with self.wake:
                if self.stopping:
                    return
                running = {job['id']: job for job in self.store.running_jobs()}
                ids = set(running) | {job_id for job_id, _ in self.processes.values()}
                for job_id in ids:
                    job = running.get(job_id) or self.store.get(job_id)
                    elapsed = seconds(job['started_at'])
                    if job['status'] in ACTIVE and elapsed is not None and elapsed >= self.timeout:
                        self.store.fail(job_id, 'Build exceeded the one-hour limit.' if self.timeout == 3600 else
                                        f'Build exceeded its {self.timeout:g}-second execution limit.')
                        self._stop_job(job_id)
                    elif job['status'] in TERMINAL:
                        self._stop_job(job_id)
                self.wake.wait(timeout=.2)

    @staticmethod
    def _terminate(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def _stop_job(self, job_id):
        for owner, process in self.processes.values():
            if owner == job_id:
                self._terminate(process)

    def close(self):
        with self.wake:
            if self.stopping:
                return
            self.stopping = True
            for _, process in self.processes.values():
                self._terminate(process)
            self.wake.notify_all()
        for thread in self.threads:
            if thread is not threading.current_thread():
                thread.join()
        if self.owner is not None:
            self.store.recover_interrupted()
            self.owner.close()
            self.owner = None
