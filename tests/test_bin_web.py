"""Gridfinity editor requests retain queue and checked-download guarantees."""
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from zipfile import ZipFile

from vault.bin_config import BinConfiguration
from vault.generator import Configuration, parse_configuration
from vault.web import handler
from vault.web_jobs import Jobs


class BinHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.jobs = Jobs(self.root, start_worker=False)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.jobs))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.jobs.close()
        self.temporary.cleanup()

    def request(self, method, path, body=None, *, origin=True):
        connection = HTTPConnection('127.0.0.1', self.port)
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = f'http://127.0.0.1:{self.port}'
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_catalog_dispatch_and_queue_recovery(self):
        for page in ('/gridfinity', '/gridfinity/'):
            status, body = self.request('GET', page)
            self.assertEqual(status, 200)
            self.assertIn(b'<html', body)
        status, body = self.request('GET', '/api/gridfinity/config')
        self.assertEqual(status, 200)
        defaults = json.loads(body)['defaults']
        config = parse_configuration(defaults)
        self.assertIsInstance(config, BinConfiguration)
        self.assertEqual(config.parts, ('gridfinity_bins',))
        self.assertNotIn('gridfinity_bins', Configuration().parts)
        self.assertEqual(self.request('POST', '/api/jobs', defaults, origin=False)[0], 403)
        status, body = self.request('POST', '/api/jobs', defaults)
        self.assertEqual(status, 202)
        job = json.loads(body)
        self.assertEqual(job['configuration'], config.as_dict())
        self.assertEqual(json.loads(self.request('POST', '/api/jobs', defaults)[1])['id'], job['id'])
        restored = Jobs(self.root, start_worker=False)
        self.addCleanup(restored.close)
        self.assertEqual(restored.get(job['id'])['status'], 'queued')
        self.assertEqual(restored.get(job['id'])['configuration'], config.as_dict())
        self.assertEqual(self.request('GET', f'/api/jobs/{job["id"]}')[0], 200)
        self.assertEqual(self.request('GET', f'/api/jobs/{job["id"]}/bundle.zip')[0], 409)

    def test_largest_full_grid_and_all_dividers_fit_bounded_request(self):
        cells = [[x, y] for y in range(7) for x in range(6)]
        dividers = ([{'axis': 'x', 'x': x, 'y': y} for y in range(7) for x in range(1, 6)]
                    + [{'axis': 'y', 'x': x, 'y': y} for y in range(1, 7) for x in range(6)])
        config = BinConfiguration.parse({
            'part': 'gridfinity_bins', 'family': 'L', 'depth_units': 7, 'height_units': 2,
            'cells': cells, 'dividers': dividers, 'wall_pattern': 'miura', 'wall_perimeters': 1})
        status, body = self.request('POST', '/api/jobs', config.as_dict())
        self.assertEqual(status, 202, body)
        self.assertEqual(json.loads(body)['configuration'], config.as_dict())
        self.assertEqual(self.request('POST', '/api/jobs', config.as_dict() | {'cells': []})[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs', config.as_dict() | {'wall_perimeters': 3})[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs', {'padding': 'x' * 8192})[0], 413)

    def test_drawer_box_requests_keep_mode_floor_and_shared_queue_guarantees(self):
        config = BinConfiguration(container_type='drawer',family='M',depth_units=5,
            drawer_floor=3.,wall_pattern='miura',wall_perimeters=2,
            dividers=({'axis':'x','x':1,'y':0},))
        status,body = self.request('POST','/api/jobs',config.as_dict())
        self.assertEqual(status,202,body)
        job = json.loads(body)
        self.assertEqual(job['configuration'],config.as_dict())
        self.assertEqual(json.loads(self.request('POST','/api/jobs',config.as_dict())[1])['id'],job['id'])
        self.assertEqual(self.request('POST','/api/jobs',config.as_dict() | {'drawer_floor':0})[0],400)
        catalog=json.loads(self.request('GET','/api/gridfinity/config')[1])
        self.assertEqual(next(f for f in catalog['families'] if f['id']=='M')['drawer_columns'],4)
        self.assertTrue(any(layout['family']=='M' and layout['drawer_floor']==3
                            for layout in catalog['drawer_layouts']))

    def saved_build(self):
        config = BinConfiguration.parse({'cells': [[0, 0], [1, 0]],
            'dividers': [{'axis': 'x', 'x': 1, 'y': 0}], 'wall_perimeters': 1})
        build_id = '20261027T010000000000Z-0123456789ab'
        path = self.root / 'builds' / build_id
        path.mkdir(parents=True)
        artifacts = {'stl/bin_1.stl': b'checked mesh', 'bin_1_print.step': b'checked STEP',
                     f'{config.slug}.step': b'checked assembly', 'printing.txt': b'Printing instructions',
                     'preview/assembly/bin_1.stl': b'preview only',
                     'source/private.step': b'private source'}
        for relative, content in artifacts.items():
            target = path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (path / 'resolved-parameters.json').write_text(json.dumps(
            {'part': config.slug, 'gridfinity_configuration': config.as_dict()}))
        (path / 'manifest.json').write_text(json.dumps({
            'passed': True, 'build_id': build_id, 'name': config.name,
            'parts': {'bin_1': {'print_bbox_mm': [83.5, 41.5, 28]}},
            'gridfinity_layout': {'recorded_height_mm': 28}, 'print_instructions': 'printing.txt',
            'checksums': {relative: hashlib.sha256(content).hexdigest()
                          for relative, content in artifacts.items()}}))
        return build_id, config

    def test_saved_history_downloads_and_zip_exclude_previews_and_sources(self):
        build_id, config = self.saved_build()
        status, data = self.request('GET', '/api/builds')
        self.assertEqual(status, 200)
        build, = json.loads(data)['builds']
        self.assertEqual(build['kind'], 'gridfinity_bins')
        self.assertEqual(build['configuration'], config.as_dict())
        self.assertEqual(build['gridfinity_layout'], {'recorded_height_mm': 28})
        self.assertEqual(build['parts'][0]['step_url'], build['parts'][0]['print_step_url'])
        status, data = self.request('GET', build['bundle_url'])
        self.assertEqual(status, 200)
        with ZipFile(BytesIO(data)) as bundle:
            self.assertEqual(json.loads(bundle.read('configuration.json')), config.as_dict())
            self.assertEqual(bundle.read('gridfinity_bins/stl/bin_1.stl'), b'checked mesh')
            self.assertIn('gridfinity_bins/printing.txt', bundle.namelist())
            self.assertFalse(any('preview/' in name or 'source/' in name for name in bundle.namelist()))
        self.assertEqual(self.request('GET', f'/files/{build_id}/source/private.step')[0], 404)
        (self.root / 'builds' / build_id / 'stl/bin_1.stl').write_bytes(b'changed')
        self.assertEqual(self.request('GET', build['parts'][0]['stl_url'])[0], 409)
        self.assertEqual(self.request('GET', build['bundle_url'])[0], 409)


if __name__ == '__main__':
    unittest.main()
