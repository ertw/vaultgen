"""Generator boundaries, queue isolation and revision-pinned downloads."""
import hashlib
import io
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import unittest
import zipfile
from unittest.mock import patch

from vault.generator import Configuration
from vault.web import handler
from vault.web_builds import BuildFiles, freshness
from vault.web_jobs import Jobs


class GeneratorTests(unittest.TestCase):
    def test_all_supported_sizes_and_no_oversize_or_untyped_values(self):
        for family in ('S', 'M', 'L'):
            for depth in range(3, 8):
                for height in (1, 2):
                    self.assertEqual(Configuration(family, depth, height).parts,
                                     ('module', 'box', 'facade', 'rails', 'runner_guides', 'runner_slides',
                                      'key', 'spring', 'runner_stop', 'facade_cap', 'key_cap', 'latch'))
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
            with patch.object(jobs, '_save', side_effect=capture), patch('vault.web_jobs.subprocess.Popen') as process:
                process.return_value.stdout = iter(['First part complete\n', 'Second part failed\n'])
                process.return_value.wait.return_value = 1
                jobs._work()
            terminal = [item for item in snapshots if item['status'] == 'failed']
            self.assertEqual(len(terminal), 1)
            self.assertEqual(terminal[0]['build_ids'], ['checked-earlier-part'])


class BuildFilesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.files = BuildFiles(self.temporary.name)

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
        history = self.files.history()
        self.assertEqual({item['kind'] for item in history}, {'runner_guides', 'runner_slides'})
        for item in history:
            self.assertEqual(item['configuration'], {'depth_units': 7, 'part': item['kind']})

    def test_universal_accessory_history_and_request_validation(self):
        from vault.generator import ACCESSORY_PARTS
        for i, kind in enumerate(ACCESSORY_PARTS):
            build_id = f'20261024T01000000000{i}Z-0123456789ab'
            path = Path(self.temporary.name) / 'builds' / build_id
            path.mkdir(parents=True)
            (path / 'manifest.json').write_text(json.dumps({
                'passed': True, 'build_id': build_id, 'checksums': {}, 'parts': {},
            }))
            (path / 'resolved-parameters.json').write_text(json.dumps({
                'part': 'snap_key' if kind == 'key' else kind,
            }))
            self.assertEqual(Configuration.parse({'part': kind}).parts, (kind,))
        history = self.files.history()
        self.assertEqual({item['kind'] for item in history}, set(ACCESSORY_PARTS))
        for item in history:
            self.assertEqual(item['configuration'], {'part': item['kind']})

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
        history = self.files.history()
        self.assertEqual({b['configuration'].get('box_floor') for b in history if b['kind'] == 'box'}, {0.8, 3})
        self.assertEqual({b['configuration'].get('module_rear') for b in history if b['kind'] == 'module'}, {0.9, 2})
        self.assertEqual({b['configuration']['drawer_columns'] for b in history if b['kind'] == 'module'}, {1})
        self.assertEqual({b['configuration']['drawer_rows'] for b in history if b['kind'] == 'module'}, {1})
        self.assertTrue(all(b['freshness']['warning'] for b in history))


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

    def test_floorless_gridfinity_submission_keeps_zero_and_rejects_plain(self):
        self.assertEqual(self.request('POST', '/api/jobs', {'part': 'box', 'box_floor': 0})[0], 400)
        request = {'part': 'box', 'box_floor': 0, 'box_variant': 'gridfinity', 'box_rear_pattern': 'waffle'}
        status, data = self.request('POST', '/api/jobs', request)
        self.assertEqual(status, 202)
        submitted = json.loads(data)['configuration']
        self.assertEqual({key: submitted[key] for key in request}, request)

    def test_assembly_endpoint_validates_selection_and_explains_empty_cache(self):
        status, data = self.request('GET', '/api/assembly?family=L&depth_units=6&height_units=2&box_floor=3&module_rear=2')
        self.assertEqual(status, 200)
        scene = json.loads(data)
        self.assertFalse(scene['complete'])
        self.assertEqual(len(scene['missing']), 29)
        self.assertEqual(scene['instances'], [])
        status, data = self.request('GET', '/api/assembly?family=L&depth_units=6&height_units=2&drawer_columns=2')
        self.assertEqual(status, 200)
        scene = json.loads(data)
        self.assertEqual(scene['name'], 'L6² · 2F complete set')
        self.assertEqual(len(scene['missing']), 51)
        status, data = self.request('GET', '/api/assembly?family=L&depth_units=6&height_units=2&drawer_columns=2&drawer_rows=2')
        self.assertEqual(status, 200)
        scene = json.loads(data)
        self.assertEqual(scene['name'], 'L6² · 2F · 4 drawers complete set')
        self.assertEqual(len(scene['missing']), 67)
        status, data = self.request('GET', '/api/assembly?wall_pattern=miura&pattern_pitch=20&pattern_depth=1.4&pattern_line_width=0.8&pattern_faces=sides&pattern_construction=corrugated')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['configuration']['pattern_pitch'], 20.)
        self.assertEqual(json.loads(data)['configuration']['wall_pattern'], 'miura')
        self.assertEqual(json.loads(data)['configuration']['pattern_construction'], 'corrugated')
        self.assertIn('corrugated', json.loads(data)['name'])
        status, data = self.request('GET', '/api/assembly?box_rear_pattern=waffle&wall_pattern=miura&box_variant=gridfinity')
        self.assertEqual(status, 200)
        configured = json.loads(data)
        self.assertEqual(configured['configuration']['box_rear_pattern'], 'waffle')
        self.assertEqual(configured['configuration']['wall_pattern'], 'miura')
        self.assertEqual(configured['configuration']['box_variant'], 'gridfinity')
        self.assertIn('Waffle corrugated box rear', configured['name'])
        status, data = self.request('GET', '/api/assembly?box_floor=0&box_variant=gridfinity&box_rear_pattern=miura')
        self.assertEqual(status, 200)
        configured = json.loads(data)
        self.assertEqual(configured['configuration']['box_floor'], 0)
        self.assertEqual(configured['configuration']['box_rear_pattern'], 'miura')
        self.assertIn('Floorless Gridfinity', configured['name'])
        for floor, expected in (('0.8', .8), ('default', 'default')):
            status, data = self.request('GET', '/api/assembly?facade_floor=' + floor)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)['configuration']['facade_floor'], expected)
        for query in ('family=XL', 'family=S&family=L', 'depth_units=4.5', 'part=box',
                      'box_floor=nan', 'box_floor=0', 'box_floor=0&box_variant=plain',
                      'facade_floor=nan', 'facade_floor=0', 'facade_floor=3', 'facade_floor=',
                      'facade_floor=0.8&facade_floor=default',
                      'module_rear=3', 'unknown=1', 'drawer_columns=2',
                      'family=L&drawer_columns=3', 'family=L&drawer_columns=2.0',
                      'family=L&drawer_columns=2&drawer_rows=2', 'family=L&height_units=2&drawer_rows=2',
                      'family=L&height_units=2&drawer_columns=2&drawer_rows=2.0',
                      'wall_pattern=unknown', 'pattern_faces=front', 'pattern_pitch=nan',
                      'wall_pattern=waffle&pattern_depth=2', 'pattern_line_width=0.3',
                      'pattern_construction=solid', 'box_rear_pattern=unknown', 'box_rear_pattern=',
                      'box_rear_pattern=plain&box_rear_pattern=waffle'):
            self.assertEqual(self.request('GET', '/api/assembly?' + query)[0], 400)

    def test_multi_drawer_submission_and_catalog_agree(self):
        status, body = self.request('GET', '/api/config')
        catalog = json.loads(body)
        self.assertEqual(catalog['defaults']['drawer_columns'], 1)
        self.assertEqual(catalog['defaults']['drawer_rows'], 1)
        self.assertTrue(all(layout['families'] == ['L'] for layout in catalog['drawer_layouts'] if layout['columns'] == 2))
        self.assertEqual(next(layout for layout in catalog['drawer_layouts'] if layout['rows'] == 2)['heights'], [2])
        status, body = self.request('POST', '/api/jobs', {'family': 'L', 'drawer_columns': 2})
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)['configuration']['drawer_columns'], 2)
        status, body = self.request('POST', '/api/jobs', {'family': 'L', 'height_units': 2, 'drawer_columns': 2, 'drawer_rows': 2})
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)['configuration']['drawer_rows'], 2)
        for values in ({'family': 'S', 'drawer_columns': 2}, {'family': 'M', 'drawer_columns': 2},
                       {'family': 'L', 'drawer_columns': True}, {'family': 'L', 'drawer_columns': 2.0},
                       {'family': 'L', 'height_units': 2, 'drawer_rows': 2},
                       {'family': 'L', 'drawer_columns': 2, 'drawer_rows': 2},
                       {'family': 'L', 'height_units': 2, 'drawer_columns': 2, 'drawer_rows': True}):
            self.assertEqual(self.request('POST', '/api/jobs', values)[0], 400)

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

    def test_multi_drawer_bundle_records_copies_and_exact_builds(self):
        for rows in (1, 2):
            with self.subTest(drawer_rows=rows):
                self.check_multi_drawer_bundle(rows)

    def check_multi_drawer_bundle(self, rows):
        configuration = Configuration(family='L', depth_units=6, height_units=2, drawer_columns=2, drawer_rows=rows)
        expected = {'module':1, 'box':2, 'facade':2, 'rails':2, 'runner_guides':4,
                    'runner_slides':4, 'key':2, 'spring':4, 'runner_stop':8,
                    'facade_cap':8, 'key_cap':2, 'latch':2}
        if rows == 2:
            expected.update(box=4, facade=4, rails=4, key=4, spring=8, key_cap=4)
        part_names = {'module':'l6_2_columns_module_2f', 'box':'s6_box_2f', 'facade':'s2f_facade',
                      'rails':'s_geared_rails', 'runner_guides':'x6_runner_guides',
                      'runner_slides':'x6_runner_slides', 'key':'snap_key'}
        build_ids = []
        for index, kind in enumerate(configuration.parts):
            build_id = f'20261024T010000{rows * 20 + index:06d}Z-0123456789ab'
            build_ids.append(build_id)
            directory = Path(self.temporary.name) / 'builds' / build_id
            checksums = {}
            filenames = ['first.stl', 'second.stl'] if kind in ('rails', 'runner_guides', 'runner_slides', 'key') else ['part.stl']
            for relative in [f'stl/{name}' for name in filenames] + ['preview/assembly/finished.stl']:
                path = directory / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'checked geometry')
                checksums[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            (directory / 'manifest.json').write_text(json.dumps({
                'passed': True, 'build_id': build_id, 'checksums': checksums, 'parts': {}}))
            (directory / 'resolved-parameters.json').write_text(json.dumps({
                'part': part_names.get(kind, kind)}))
        job = self.jobs.submit(configuration)
        self.jobs.items[job['id']].update(status='completed', build_ids=build_ids)
        status, data = self.request('GET', f'/api/jobs/{job["id"]}/bundle.zip')
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            plan = json.loads(bundle.read('print-plan.json'))
            self.assertEqual(plan['configuration'], configuration.as_dict())
            self.assertEqual(len(plan['files']), 16)
            self.assertEqual({item['build_id'] for item in plan['files']}, set(build_ids))
            self.assertEqual({item['kind']:item['copies'] for item in plan['files']}, expected)
            self.assertTrue(all(item['path'] in bundle.namelist() for item in plan['files']))
            self.assertTrue(all(item['optional'] == (item['kind'] == 'key_cap') for item in plan['files']))
            self.assertFalse(any('/preview/' in name for name in bundle.namelist()))
            self.assertIn('4 × runner_guides/stl/first.stl', bundle.read('PRINTING.txt').decode())


if __name__ == '__main__':
    unittest.main()
