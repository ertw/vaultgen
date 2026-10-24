"""Vault generator: loopback HTTP, isolated queued CAD jobs, immutable downloads."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.parse import unquote, urlsplit
import uuid
import zipfile

from .generator import Configuration, catalog
from .reference import PROJECT_ROOT

STATIC = Path(__file__).with_name('static')
BUILD_ID = re.compile(r'\d{8}T\d{12}Z-[a-f0-9]{12}')
JOB_ID = re.compile(r'[a-f0-9]{32}')
PUBLIC_SUFFIXES = {'.stl', '.step', '.png'}


def now():
    return datetime.now(timezone.utc).isoformat()


class BuildFiles:
    def __init__(self, output):
        self.root = Path(output).resolve() / 'builds'

    def read(self, build_id):
        if not BUILD_ID.fullmatch(build_id):
            raise FileNotFoundError('Unknown build')
        path = self.root / build_id
        if path.resolve().parent != self.root:
            raise FileNotFoundError('Unknown build')
        file = path / 'manifest.json'
        if not file.resolve().is_relative_to(path):
            raise FileNotFoundError('Unknown build')
        manifest = json.loads(file.read_text())
        if manifest.get('passed') is not True or manifest.get('build_id') != build_id:
            raise FileNotFoundError('Build has not passed validation')
        return path, manifest

    def artifact(self, build_id, relative):
        path, manifest = self.read(build_id)
        file = path / relative
        if (not relative or relative.startswith('/') or '..' in Path(relative).parts
                or relative.startswith('source/') or file.suffix not in PUBLIC_SUFFIXES
                or not file.resolve().is_relative_to(path)
                or relative not in manifest['checksums']):
            raise FileNotFoundError('Unknown artifact')
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest['checksums'][relative]:
            raise ValueError('Artifact checksum failed; generate a fresh build')
        return data

    def describe(self, build_id):
        path, manifest = self.read(build_id)
        parameters = json.loads((path / 'resolved-parameters.json').read_text())
        part = parameters.get('part', '')
        kind = ('rails' if part.endswith('_geared_rails') else
                'facade' if part.endswith('_facade') else
                'box' if '_box_' in part else 'module')
        config = {key: parameters[key] for key in ('family', 'depth_units', 'height_units')
                  if key in parameters}
        config['part'] = kind
        def url(relative):
            return f'/files/{build_id}/{relative}' if relative in manifest['checksums'] else None
        parts = []
        for name, details in manifest.get('parts', {}).items():
            parts.append({'name': name, 'print_bbox_mm': details.get('print_bbox_mm', []),
                          'print_note': details.get('print_note', ''),
                          'stl_url': url(f'stl/{name}.stl'),
                          'step_url': url(f'{name}_print.step')})
        return {'id': build_id, 'name': manifest.get('name', part), 'kind': kind,
                'configuration': config, 'parts': parts, 'step_url': url(f'{part}.step'),
                'preview_url': url('review/isometric.png'),
                'created_at': datetime.strptime(build_id[:22], '%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc).isoformat()}

    def history(self):
        result = []
        for path in sorted(self.root.glob('*'), reverse=True):
            try:
                item = self.describe(path.name)
                config = item['configuration']
                if (config.get('family') in ('S', 'M', 'L')
                        and config.get('height_units', 1) in (1, 2)
                        and config.get('depth_units', 4) in range(3, 8)):
                    result.append(item)
            except (OSError, ValueError, KeyError):
                continue
            if len(result) == 100:
                break
        return result


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
                if len(build_ids) != len(Configuration.parse(item['configuration']).parts):
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


def handler(jobs):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'VaultGen/1'

        def send(self, status, body, mime='application/json; charset=utf-8', filename=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            try:
                if path == '/healthz':
                    return self.send(200, {'status': 'ok'})
                if path == '/api/config':
                    return self.send(200, catalog())
                if path == '/api/builds':
                    return self.send(200, {'builds': jobs.files.history()})
                if path == '/api/jobs':
                    return self.send(200, {'jobs': jobs.history()})
                if path.startswith('/api/jobs/'):
                    pieces = path.strip('/').split('/')
                    if len(pieces) == 3:
                        return self.send(200, jobs.get(pieces[2]))
                    if len(pieces) == 4 and pieces[3] == 'bundle.zip':
                        return self.bundle(pieces[2])
                    raise FileNotFoundError('Unknown endpoint')
                if path.startswith('/files/'):
                    _, _, build_id, relative = path.split('/', 3)
                    data = jobs.files.artifact(build_id, relative)
                    mime = mimetypes.guess_type(relative)[0] or 'application/octet-stream'
                    return self.send(200, data, mime,
                                     Path(relative).name if not relative.endswith('.png') else None)
                relative = 'index.html' if path == '/' else path.removeprefix('/static/')
                file = STATIC / relative
                if (path != '/' and not path.startswith('/static/')) or not file.resolve().is_relative_to(STATIC.resolve()):
                    raise FileNotFoundError('Unknown page')
                return self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            except (OSError, KeyError, IndexError):
                self.send(404, {'error': 'Build or file not found'})
            except ValueError as error:
                self.send(409, {'error': str(error)})

        def bundle(self, job_id):
            job = jobs.get(job_id)
            if job['status'] != 'completed':
                raise ValueError('This set has not completed')
            with tempfile.TemporaryFile() as archive:
                with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
                    bundle.writestr('configuration.json', json.dumps(job['configuration'], indent=2))
                    for build in job['builds']:
                        _, manifest = jobs.files.read(build['id'])
                        for relative in manifest['checksums']:
                            if relative.startswith('source/') or Path(relative).suffix not in {'.stl', '.step'}:
                                continue
                            bundle.writestr(f'{build["kind"]}/{relative}', jobs.files.artifact(build['id'], relative))
                    bundle.writestr('parts.json', json.dumps(job['builds'], indent=2))
                size = archive.tell()
                archive.seek(0)
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Length', str(size))
                self.send_header('Content-Disposition', f'attachment; filename="vault-{job_id[:8]}.zip"')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                if self.command != 'HEAD':
                    while chunk := archive.read(1024 * 1024):
                        self.wfile.write(chunk)

        def do_POST(self):
            origin = urlsplit(self.headers.get('Origin', ''))
            if (origin.scheme not in ('http', 'https') or origin.netloc != self.headers.get('Host')
                    or self.headers.get('Sec-Fetch-Site', 'same-origin') not in ('same-origin', 'none')):
                return self.send(403, {'error': 'Same-origin request required'})
            if self.path != '/api/jobs':
                return self.send(404, {'error': 'Unknown endpoint'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'Use application/json'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    return self.send(413, {'error': 'Request must contain at most 4096 bytes'})
                value = json.loads(self.rfile.read(length))
                config = Configuration.parse(value)
                return self.send(202, jobs.submit(config))
            except (ValueError, TypeError) as error:
                self.send(400, {'error': str(error)})
            except OverflowError as error:
                self.send(429, {'error': str(error)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1', choices=['127.0.0.1'])
    parser.add_argument('--port', type=int, default=3941)
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'out')
    args = parser.parse_args()
    jobs = Jobs(args.output)
    server = ThreadingHTTPServer((args.host, args.port), handler(jobs))
    print(f'Vault generator: http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        jobs.close()
        server.server_close()


if __name__ == '__main__':
    main()
