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
from vault.web import BuildFiles, Jobs, handler, freshness


class GeneratorTests(unittest.TestCase):
    def test_all_supported_sizes_and_no_oversize_or_untyped_values(self):
        for family in ('S', 'M', 'L'):
            for depth in range(3, 8):
                for height in (1, 2):
                    self.assertEqual(Configuration(family, depth, height).parts,
                                     ('module', 'box', 'facade', 'rails', 'runner_guides', 'runner_slides'))
        for values in ({'family': 'XL'}, {'height_units': 4}, {'depth_units': 8},
                       {'depth_units': 2}, {'height_units': True}, {'depth_units': 4.0},
                       {'part': '../x'}, {'part': []}, {'command': 'whoami'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Configuration.parse(values)

    def test_thickness_options_and_revision_warnings(self):
        self.assertEqual(Configuration().box_floor, 0.8)
        self.assertEqual(Configuration().module_rear, 0.9)
        self.assertEqual(Configuration.parse({'box_floor': 3, 'module_rear': 2}).box_floor, 3)
        for values in ({'box_floor': True}, {'box_floor': 2}, {'module_rear': 3}, {'module_rear': None}):
            with self.assertRaises(ValueError):
                Configuration.parse(values)
        current = {'commit': 'new', 'dirty': False}
        self.assertFalse(freshness({'git': current}, current)['warning'])
        for built, repo in (({'commit': 'old'}, current), ({}, current),
                            (current, None), (current, dict(current, dirty=True)),
                            (dict(current, dirty=True), current)):
            self.assertTrue(freshness({'git': built}, repo)['warning'])

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
        parts = {item['id'] for item in json.loads(body)['parts']}
        self.assertTrue({'runner_guides', 'runner_slides'} <= parts)
        for kind in ('runner_guides', 'runner_slides'):
            status, body = self.request('POST', '/api/jobs', {'part': kind, 'depth_units': 7})
            self.assertEqual(status, 202)
            self.assertEqual(json.loads(body)['configuration']['part'], kind)

    def test_assembly_endpoint_validates_selection_and_explains_empty_cache(self):
        status, data = self.request('GET', '/api/assembly?family=L&depth_units=6&height_units=2&box_floor=3&module_rear=2')
        self.assertEqual(status, 200)
        scene = json.loads(data)
        self.assertFalse(scene['complete'])
        self.assertEqual(len(scene['missing']), 13)
        self.assertEqual(scene['instances'], [])
        for query in ('family=XL', 'family=S&family=L', 'depth_units=4.5', 'part=box',
                      'box_floor=nan', 'module_rear=3', 'unknown=1'):
            self.assertEqual(self.request('GET', '/api/assembly?' + query)[0], 400)

    def test_runner_history_preserves_depth_without_inventing_a_width_family(self):
        for i, kind in enumerate(('runner_guides', 'runner_slides')):
            build_id = f'20261024T01000000000{i}Z-0123456789ab'
            path = Path(self.temporary.name) / 'builds' / build_id
            path.mkdir(parents=True)
            (path / 'manifest.json').write_text(json.dumps({
                'passed': True, 'build_id': build_id, 'checksums': {},
                'parts': {f'x7_{kind}_left': {'kind': kind}},
            }))
            (path / 'resolved-parameters.json').write_text(json.dumps({
                'depth_units': 7, 'part': f'x7_{kind}',
            }))
        history = BuildFiles(self.temporary.name).history()
        self.assertEqual({item['kind'] for item in history}, {'runner_guides', 'runner_slides'})
        for item in history:
            self.assertEqual(item['configuration'], {'depth_units': 7, 'part': item['kind']})

    def test_history_distinguishes_thickness_variants_and_legacy_defaults(self):
        for i, (kind, key, value, suffix) in enumerate((
                ('box', 'box_floor', None, ''), ('box', 'box_floor', 3, '_floor_3mm'),
                ('module', 'module_rear', None, ''), ('module', 'module_rear', 2, '_rear_2mm'))):
            build_id = f'20261024T01000000000{i}Z-0123456789ab'
            path = Path(self.temporary.name) / 'builds' / build_id
            path.mkdir(parents=True)
            (path / 'manifest.json').write_text(json.dumps({
                'passed': True, 'build_id': build_id, 'checksums': {}, 'parts': {}}))
            parameters = dict(family='L', depth_units=6, height_units=2,
                              part=f'l6_{kind}_2f{suffix}')
            if value is not None:
                parameters[key] = value
            (path / 'resolved-parameters.json').write_text(json.dumps(parameters))
        history = self.jobs.files.history()
        self.assertEqual({b['configuration'].get('box_floor') for b in history if b['kind'] == 'box'}, {0.8, 3})
        self.assertEqual({b['configuration'].get('module_rear') for b in history if b['kind'] == 'module'}, {0.9, 2})
        self.assertTrue(all(b['freshness']['warning'] for b in history))

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
