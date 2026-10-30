"""Label requests share the bounded queue and immutable download guarantees."""
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

from vault.generator import Configuration, parse_configuration
from vault.label_config import LabelConfiguration, label_dimensions, label_layout
from vault.web import handler
from vault.web_jobs import Jobs


def request_configuration(**changes):
    return dict(part='label', lines=[dict(text='BOLTS', size=6, color='#ffffff')],
                background='#30343b', hollow=True) | changes


class LabelConfigurationTests(unittest.TestCase):
    def test_label_dispatch_round_trips_without_changing_complete_sets(self):
        config = parse_configuration(request_configuration(lines=[
            dict(text='BOLTS', size=6, color='#ffffff'),
            dict(text='M3', size=4, color='#ff9900')]))
        self.assertIsInstance(config, LabelConfiguration)
        self.assertEqual(config.parts, ('label',))
        self.assertEqual(parse_configuration(config.as_dict()), config)
        self.assertNotIn('label', Configuration().parts)
        self.assertIsInstance(parse_configuration({}), Configuration)

    def test_invalid_label_requests_fail_before_queueing(self):
        valid = request_configuration()
        cases = [
            valid | {'lines': []},
            valid | {'lines': valid['lines'] * 3},
            valid | {'lines': 'BOLTS'},
            valid | {'lines': [None]},
            valid | {'lines': [dict(text='', size=6, color='#ffffff')]},
            valid | {'lines': [dict(text='BOLTS', size=True, color='#ffffff')]},
            valid | {'lines': [dict(text='BOLTS', size=float('nan'), color='#ffffff')]},
            valid | {'lines': [dict(text='BOLTS', size=1000, color='#ffffff')]},
            valid | {'lines': [dict(text='BOLTS', size=10**400, color='#ffffff')]},
            valid | {'lines': [dict(text='BOLTS', size=6, color='red')]},
            valid | {'lines': [dict(text='BOLTS', size=6, color='#30343b')]},
            valid | {'lines': [dict(text='BOLTS', size=6, color='#ffffff'),
                               dict(text='M3', size=4, color='#30343b')]},
            valid | {'lines': [dict(text='BOLTS', size=6, color='#ffffff', command='x')]},
            valid | {'background': '#ffffff'},
            valid | {'background': []},
            valid | {'hollow': 'false'},
            valid | {'font': '/tmp/arbitrary.ttf'},
            valid | {'lines': [dict(text='A\nB', size=6, color='#ffffff')]},
            valid | {'lines': [dict(text='A\x00B', size=6, color='#ffffff')]},
            valid | {'lines': [dict(text='🔩', size=6, color='#ffffff')]},
            *(valid | {'family': family} for family in ('XL', 'm', '', None, 1, True, [], {})),
            valid | {'family': LabelConfiguration(family='M')},
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_configuration(value)

    def test_family_selection_changes_width_and_center_without_scaling_letters(self):
        legacy = parse_configuration(request_configuration())
        self.assertEqual(legacy.family, 'S')
        self.assertEqual(legacy.as_dict()['family'], 'S')
        self.assertEqual(legacy, parse_configuration(request_configuration(family='S')))
        configs = [parse_configuration(request_configuration(family=family))
                   for family in ('S', 'M', 'L')]
        self.assertEqual(len({config.key for config in configs}), 3)
        self.assertEqual(len({config.slug for config in configs}), 3)
        original = label_layout(configs[0])[0]
        for config, width in zip(configs, (47., 91.6, 129.4)):
            with self.subTest(family=config.family):
                dimensions = label_dimensions(config)
                self.assertAlmostEqual(dimensions['width_mm'], width)
                self.assertEqual(dimensions['height_mm'], 19.4)
                line, = label_layout(config)
                self.assertEqual(line['scale'], original['scale'])
                self.assertEqual(line['bounds'], original['bounds'])
                self.assertEqual(line['baseline_y'], original['baseline_y'])
                self.assertAlmostEqual(line['x'] + (line['bounds'][0] + line['bounds'][2])/2,
                                       width/2)

    def test_long_text_uses_family_width_and_the_96_character_limit(self):
        def config(family, length):
            return parse_configuration(request_configuration(family=family,
                lines=[dict(text='i' * length, size=3, color='#ffffff')]))
        self.assertEqual(len(config('M', 64).lines[0].text), 64)
        self.assertEqual(len(config('L', 96).lines[0].text), 96)
        for family, length in (('S', 64), ('M', 96), ('L', 97)):
            with self.subTest(family=family, length=length), self.assertRaises(ValueError):
                config(family, length)

    def test_family_jobs_are_distinct_and_legacy_s_requests_deduplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = Jobs(directory, start_worker=False)
            submitted = {family: jobs.submit(parse_configuration(
                request_configuration(family=family))) for family in ('S', 'M', 'L')}
            self.assertEqual(len({job['id'] for job in submitted.values()}), 3)
            self.assertEqual(jobs.submit(parse_configuration(request_configuration()))['id'],
                             submitted['S']['id'])
            for family, job in submitted.items():
                again = jobs.submit(parse_configuration(request_configuration(family=family)))
                self.assertEqual(again['id'], job['id'])
            restored = Jobs(directory, start_worker=False)
            for family, job in submitted.items():
                saved = restored.get(job['id'])
                self.assertEqual(saved['configuration']['family'], family)
                self.assertEqual(saved['status'], 'queued')

    def test_label_jobs_deduplicate_and_share_drawer_queue_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = Jobs(directory, start_worker=False)
            config = parse_configuration(request_configuration())
            first = jobs.submit(config)
            self.assertEqual(jobs.submit(config)['id'], first['id'])
            jobs.submit(Configuration())
            jobs.submit(parse_configuration(request_configuration(hollow=False)))
            jobs.submit(parse_configuration(request_configuration(background='#003344')))
            with self.assertRaises(OverflowError):
                jobs.submit(Configuration(depth_units=3))
            restored = Jobs(directory, start_worker=False)
            interrupted = restored.get(first['id'])
            self.assertEqual(interrupted['status'], 'queued')
            self.assertEqual(interrupted['configuration'], config.as_dict())


class LabelHTTPTests(unittest.TestCase):
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
        self.temporary.cleanup()

    def request(self, method, path, body=None, *, origin=True):
        connection = HTTPConnection('127.0.0.1', self.port)
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = f'http://127.0.0.1:{self.port}'
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        result = response.status, response.read(), response.getheader('Content-Type')
        connection.close()
        return result

    def label_build(self, *, family='S', legacy=False, serial=0, dimensions=None):
        config = parse_configuration(request_configuration(family=family)).as_dict()
        if legacy:
            config.pop('family')
        build_id = f'20261025T010000{serial:06d}Z-0123456789ab'
        path = self.root / 'builds' / build_id
        path.mkdir(parents=True)
        artifacts = {
            'label.3mf': b'checked multicolor assembly',
            'printing.txt': b'Keep the face on the bed and assign filaments to named parts.',
            'stl/shell.stl': b'checked shell',
            'stl/letters.stl': b'checked letters',
            'shell_print.step': b'checked shell STEP',
            'letters_print.step': b'checked letters STEP',
            'example_label.step': b'checked complete STEP',
            'preview/assembly/label.stl': b'preview only',
            'source/private.3mf': b'private source',
        }
        for name, content in artifacts.items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (path / 'resolved-parameters.json').write_text(json.dumps(
            dict(part='example_label', label_configuration=config)))
        (path / 'manifest.json').write_text(json.dumps(dict(
            passed=True, build_id=build_id, name='BOLTS label',
            multicolor_3mf='label.3mf', print_instructions='printing.txt',
            **({'label_dimensions': dimensions} if dimensions is not None else {}),
            parts={'shell': dict(color='#30343b', role='background'),
                   'letters': dict(color='#ffffff', role='text')},
            checksums={name: hashlib.sha256(content).hexdigest()
                       for name, content in artifacts.items()})))
        return build_id, config

    def test_editor_catalog_and_submission_preserve_text_as_data(self):
        status, page, mime = self.request('GET', '/labels')
        self.assertEqual(status, 200)
        self.assertIn('text/html', mime)
        self.assertIn(b'<html', page)
        status, body, _ = self.request('GET', '/api/labels/config')
        self.assertEqual(status, 200)
        catalog = json.loads(body)
        self.assertEqual(catalog['defaults']['family'], 'S')
        self.assertEqual(catalog['max_characters_per_line'], 96)
        self.assertEqual({item['id']: item['dimensions']['width_mm']
                          for item in catalog['families']}, {'S':47., 'M':91.6, 'L':129.4})
        value = request_configuration(lines=[dict(text='<&>', size=6, color='#ffffff')])
        self.assertEqual(self.request('POST', '/api/jobs', value, origin=False)[0], 403)
        status, body, mime = self.request('POST', '/api/jobs', value)
        self.assertEqual(status, 202)
        self.assertIn('application/json', mime)
        job = json.loads(body)
        self.assertEqual(job['configuration']['lines'][0]['text'], '<&>')
        self.assertEqual(job['configuration']['part'], 'label')
        self.assertEqual(self.request('GET', f'/api/jobs/{job["id"]}')[0], 200)
        self.assertEqual(self.request('GET', f'/api/jobs/{job["id"]}/bundle.zip')[0], 409)
        self.assertEqual(self.request('POST', '/api/jobs', value | {'hollow': 'yes'})[0], 400)

    def test_http_requests_preserve_family_and_allow_long_labels(self):
        for family, length in (('M', 64), ('L', 96)):
            value = request_configuration(family=family,
                lines=[dict(text='i' * length, size=3, color='#ffffff')])
            status, body, _ = self.request('POST', '/api/jobs', value)
            self.assertEqual(status, 202)
            saved = json.loads(body)['configuration']
            self.assertEqual(saved['family'], family)
            self.assertEqual(saved['lines'][0]['text'], 'i' * length)
        for family in ('XL', None, []):
            self.assertEqual(self.request('POST', '/api/jobs',
                                         request_configuration(family=family))[0], 400)

    def test_legacy_and_family_history_remain_distinct_and_downloadable(self):
        expected = {}
        recorded_dimensions = {}
        for serial, family in enumerate(('S', 'M', 'L')):
            dimensions = None if family == 'S' else label_dimensions(family)
            if family == 'L':
                # A historical build's measurements need not match today's
                # constructors; the saved geometry remains authoritative.
                dimensions = dimensions | {'width_mm':129.25}
            build_id, config = self.label_build(family=family, legacy=family == 'S',
                                                serial=serial, dimensions=dimensions)
            expected[build_id] = config
            recorded_dimensions[build_id] = dimensions
        status, body, _ = self.request('GET', '/api/builds')
        self.assertEqual(status, 200)
        builds = json.loads(body)['builds']
        self.assertEqual({build['id'] for build in builds}, set(expected))
        self.assertEqual({build['configuration'].get('family', 'S') for build in builds}, {'S','M','L'})
        for build in builds:
            self.assertEqual(build['configuration'], expected[build['id']])
            self.assertEqual(build['label_dimensions'], recorded_dimensions[build['id']])
            status, data, _ = self.request('GET', build['bundle_url'])
            self.assertEqual(status, 200)
            with zipfile.ZipFile(BytesIO(data)) as bundle:
                self.assertEqual(json.loads(bundle.read('configuration.json')), expected[build['id']])
                self.assertEqual(bundle.read('label/label.3mf'), b'checked multicolor assembly')

    def test_history_and_downloads_retain_materials_and_check_checksums(self):
        build_id, config = self.label_build()
        status, body, _ = self.request('GET', '/api/builds')
        self.assertEqual(status, 200)
        build, = json.loads(body)['builds']
        self.assertEqual(build['configuration'], config)
        self.assertEqual(build['kind'], 'label')
        self.assertEqual({item['color'] for item in build['parts']}, {'#30343b', '#ffffff'})
        self.assertEqual({item['role'] for item in build['parts']}, {'background', 'text'})
        self.assertEqual(self.request('GET', build['three_mf_url'])[:2],
                         (200, b'checked multicolor assembly'))
        self.assertEqual(self.request('GET', build['instructions_url'])[0], 200)
        self.assertEqual(self.request('GET', f'/files/{build_id}/source/private.3mf')[0], 404)
        self.assertEqual(self.request('GET', f'/files/{build_id}/../label.3mf')[0], 404)
        (self.root / 'builds' / build_id / 'label.3mf').write_bytes(b'changed')
        self.assertEqual(self.request('GET', build['three_mf_url'])[0], 409)
        self.assertEqual(self.request('GET', build['bundle_url'])[0], 409)

    def test_saved_label_bundle_does_not_depend_on_a_job_record(self):
        build_id, config = self.label_build()
        build = self.jobs.files.describe(build_id)
        self.assertEqual(self.jobs.history(), [])
        status, body, _ = self.request('GET', build['bundle_url'])
        self.assertEqual(status, 200)
        with zipfile.ZipFile(BytesIO(body)) as bundle:
            self.assertEqual(bundle.read('label/label.3mf'), b'checked multicolor assembly')
            self.assertEqual(json.loads(bundle.read('configuration.json')), config)
        self.assertEqual(self.request('HEAD', build['bundle_url'])[:2], (200, b''))
        self.assertEqual(self.request('GET', '/api/builds/not-a-build/bundle.zip')[0], 404)

    def test_completed_bundle_includes_registered_colors_and_instructions(self):
        build_id, config = self.label_build()
        job = self.jobs.submit(parse_configuration(config))
        with self.jobs.store.transaction() as db:
            stored = self.jobs.store._job(db, job['id'])
            stored.update(status='completed', build_ids=[build_id])
            self.jobs.store._write_job(db, stored)
        status, body, _ = self.request('GET', f'/api/jobs/{job["id"]}/bundle.zip')
        self.assertEqual(status, 200)
        with zipfile.ZipFile(BytesIO(body)) as bundle:
            names = set(bundle.namelist())
            self.assertTrue({'label/label.3mf', 'label/printing.txt',
                             'label/stl/shell.stl', 'label/stl/letters.stl',
                             'label/example_label.step'} <= names)
            self.assertFalse(any('/source/' in name or '/preview/' in name for name in names))
            self.assertEqual(json.loads(bundle.read('configuration.json')), config)


if __name__ == '__main__':
    unittest.main()
