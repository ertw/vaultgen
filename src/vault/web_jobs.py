"""Persistent generator queue and isolated CAD subprocess lifecycle."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import uuid

from .generator import parse_configuration
from .project import PROJECT_ROOT
from .web_builds import BuildFiles


JOB_ID = re.compile(r'[a-f0-9]{32}')


def now():
    return datetime.now(timezone.utc).isoformat()


class Jobs:
    def __init__(self, output, *, start_worker=True, timeout=3600):
        self.output = Path(output).resolve()
        self.state = self.output / 'web'
        self.state.mkdir(parents=True, exist_ok=True)
        self.files = BuildFiles(output)
        self.lock = threading.RLock()
        self.pending = queue.Queue()
        self.timeout = timeout
        self.items = {}
        self.process = None
        self.stopping = False
        for file in sorted(self.state.glob('*.json')):
            if not JOB_ID.fullmatch(file.stem):
                continue
            try:
                item = json.loads(file.read_text())
                if item['status'] in ('queued', 'running'):
                    item.update(status='failed', error='The service restarted. Generate again to resume using completed parts.')
                self.items[item['id']] = item
            except (ValueError, KeyError, OSError):
                continue
        if start_worker:
            threading.Thread(target=self._work, daemon=True).start()

    def _save(self, item):
        temporary = self.state / (item['id'] + '.tmp')
        temporary.write_text(json.dumps(item))
        temporary.replace(self.state / (item['id'] + '.json'))

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
        with self.lock:
            if job_id not in self.items:
                raise FileNotFoundError('Unknown job')
            return self.describe(self.items[job_id])

    def history(self):
        with self.lock:
            return [self.describe(item) for item in sorted(self.items.values(),
                    key=lambda item: item['created_at'], reverse=True)[:30]]

    def submit(self, config):
        with self.lock:
            for item in self.items.values():
                if item['status'] in ('queued', 'running') and item['configuration'] == config.as_dict():
                    return self.describe(item)
            if sum(item['status'] in ('queued', 'running') for item in self.items.values()) >= 4:
                raise OverflowError('The build queue is full. Wait for a build to finish.')
            item = {'id': uuid.uuid4().hex, 'configuration': config.as_dict(),
                    'created_at': now(), 'status': 'queued', 'logs': '',
                    'error': None, 'build_ids': []}
            self.items[item['id']] = item
            self._save(item)
            self.pending.put(item['id'])
            return self.describe(item)

    def _update(self, item, **values):
        with self.lock:
            item.update(values)
            self._save(item)

    def _work(self):
        while not self.stopping:
            job_id = self.pending.get()
            if job_id is None:
                return
            item = self.items[job_id]
            receipt = self.state / (job_id + '.receipt')
            self._update(item, status='running')
            timer = None
            expired = threading.Event()
            terminal = {'status': 'failed', 'error': 'Build interrupted'}
            try:
                command = [sys.executable, '-u', '-m', 'vault.web_worker',
                           '--configuration', json.dumps(item['configuration']),
                           '--output', str(self.output), '--receipt', str(receipt)]
                process = subprocess.Popen(command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, start_new_session=True)
                self.process = process
                def timeout():
                    expired.set()
                    self._terminate(process)
                timer = threading.Timer(self.timeout, timeout)
                timer.daemon = True
                timer.start()
                for line in process.stdout:
                    self._update(item, logs=(item['logs'] + line)[-40000:])
                code = process.wait()
                if code:
                    raise RuntimeError('Build exceeded the one-hour limit.' if expired.is_set()
                                       else 'CAD generation failed. See the build log; completed parts remain available.')
                if not receipt.is_file():
                    raise RuntimeError('CAD worker did not publish a receipt')
                build_ids = json.loads(receipt.read_text())
                for build_id in build_ids:
                    self.files.describe(build_id)
                if len(build_ids) != len(parse_configuration(item['configuration']).parts):
                    raise RuntimeError('CAD worker did not complete every requested part')
                terminal = {'status': 'completed', 'error': None, 'build_ids': build_ids}
            except Exception as error:
                terminal = {'status': 'failed', 'error': str(error)}
            finally:
                if timer:
                    timer.cancel()
                self.process = None
                if receipt.is_file():
                    try:
                        terminal['build_ids'] = json.loads(receipt.read_text())
                    except (OSError, ValueError):
                        pass
                # Publish terminal state and partial results together. Clients
                # stop polling at failure and must not miss checked earlier parts.
                self._update(item, **terminal)
                self.pending.task_done()

    @staticmethod
    def _terminate(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close(self):
        self.stopping = True
        self.pending.put(None)
        if self.process:
            self._terminate(self.process)
