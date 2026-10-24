"""Generator boundaries, queue isolation and revision-pinned downloads."""
import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch

from vault.generator import Configuration
from vault.web import BuildFiles, Jobs, handler


class GeneratorTests(unittest.TestCase):
    def test_all_supported_sizes_and_no_oversize_or_untyped_values(self):
        for family in ('S', 'M', 'L'):
            for depth in range(3, 8):
                for height in (1, 2):
                    self.assertEqual(len(Configuration(family, depth, height).parts), 4)
        for values in ({'family': 'XL'}, {'height_units': 4}, {'depth_units': 8},
                       {'depth_units': 2}, {'height_units': True}, {'depth_units': 4.0},
                       {'part': '../x'}, {'part': []}, {'command': 'whoami'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Configuration.parse(values)

    def test_queue_deduplicates_and_bounds_pending_work(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = Jobs(directory, start_worker=False)
            first = jobs.submit(Configuration())
            self.assertEqual(jobs.submit(Configuration())['id'], first['id'])
            for depth in (3, 5, 6):
                jobs.submit(Configuration(depth_units=depth))
            with self.assertRaises(OverflowError):
                jobs.submit(Configuration(depth_units=7))
            restored = Jobs(directory, start_worker=False)
            self.assertEqual(restored.get(first['id'])['status'], 'failed')
            self.assertIn('restarted', restored.get(first['id'])['error'])

    def test_failed_set_publishes_partial_receipt_with_terminal_state(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = Jobs(directory, start_worker=False)
            job = jobs.submit(Configuration())
            (jobs.state / (job['id'] + '.receipt')).write_text(json.dumps(['checked-earlier-part']))
            jobs.pending.put(None)
            snapshots = []
            save = jobs._save
            def capture(item):
                snapshots.append(json.loads(json.dumps(item)))
                save(item)
            with patch.object(jobs, '_save', side_effect=capture), patch('vault.web.subprocess.Popen') as process:
                process.return_value.stdout = iter(['First part complete\n', 'Second part failed\n'])
                process.return_value.wait.return_value = 1
                jobs._work()
            terminal = [item for item in snapshots if item['status'] == 'failed']
            self.assertEqual(len(terminal), 1)
            self.assertEqual(terminal[0]['build_ids'], ['checked-earlier-part'])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.jobs = Jobs(self.temporary.name, start_worker=False)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.jobs))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def request(self, method, path, body=None, origin=True):
        connection = HTTPConnection('127.0.0.1', self.port)
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = f'http://127.0.0.1:{self.port}'
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        data = response.read()
        result = response.status, data
        connection.close()
        return result

    def test_http_build_validation_and_origin(self):
        self.assertEqual(self.request('POST', '/api/jobs', {}, origin=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/jobs', {'family': 'XL'})[0], 400)
        status, body = self.request('POST', '/api/jobs', {'family': 'L', 'height_units': 2})
        self.assertEqual(status, 202)
        job = json.loads(body)
        self.assertEqual(job['status'], 'queued')
        self.assertEqual(self.request('GET', f'/api/jobs/{job["id"]}')[0], 200)
        self.assertEqual(self.request('GET', f'/api/jobs/{job["id"]}/bundle.zip')[0], 409)
        self.assertEqual(self.request('GET', '/static/../../pyproject.toml')[0], 404)
        status, body = self.request('GET', '/api/config')
        self.assertEqual(status, 200)
        self.assertEqual([x['id'] for x in json.loads(body)['families']], ['S', 'M', 'L'])

    def test_downloads_are_checked_and_cannot_expose_sources(self):
        build_id = '20261024T010000000000Z-0123456789ab'
        path = Path(self.temporary.name) / 'builds' / build_id
        (path / 'stl').mkdir(parents=True)
        (path / 'source').mkdir()
        artifact = path / 'stl' / 'part.stl'
        artifact.write_bytes(b'checked geometry')
        source = path / 'source' / 'private.step'
        source.write_bytes(b'private source')
        checksums = {str(file.relative_to(path)): hashlib.sha256(file.read_bytes()).hexdigest()
                     for file in (artifact, source)}
        (path / 'manifest.json').write_text(json.dumps({'passed': True,
            'build_id': build_id, 'checksums': checksums}))
        prefix = f'/files/{build_id}/'
        self.assertEqual(self.request('GET', prefix + 'stl/part.stl'), (200, b'checked geometry'))
        self.assertEqual(self.request('GET', prefix + 'source/private.step')[0], 404)
        self.assertEqual(self.request('GET', prefix + '../private.step')[0], 404)
        artifact.write_bytes(b'changed geometry')
        self.assertEqual(self.request('GET', prefix + 'stl/part.stl')[0], 409)


if __name__ == '__main__':
    unittest.main()
