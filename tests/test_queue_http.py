"""Queue HTTP behavior, including authenticated-origin mutations and pagination."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import tempfile
import threading
import unittest

from vault.web import handler
from vault.web_jobs import Jobs


class QueueHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.jobs = Jobs(self.temp.name, start_worker=False)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.jobs))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.jobs.close()
        self.temp.cleanup()

    def request(self, method, path, value=None, *, origin=True):
        port = self.server.server_port
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = f'http://127.0.0.1:{port}'
        connection = HTTPConnection('127.0.0.1', port)
        connection.request(method, path, None if value is None else json.dumps(value), headers)
        response = connection.getresponse()
        body = response.read()
        content = json.loads(body) if 'application/json' in response.getheader('Content-Type', '') else body
        connection.close()
        return response.status, content

    def test_queue_summary_details_and_pagination(self):
        ids = [self.request('POST', '/api/jobs', {'part': kind})[1]['id']
               for kind in ('spring', 'runner_stop')]
        status, queue = self.request('GET', '/api/queue?status=active&limit=1&offset=0')
        self.assertEqual(status, 200)
        self.assertEqual(queue['total'], 2)
        self.assertEqual(queue['workers'], 2)
        self.assertEqual(queue['counts']['queued'], 2)
        self.assertEqual([job['id'] for job in queue['jobs']], ids[:1])
        self.assertNotIn('logs', queue['jobs'][0])
        self.assertEqual(self.request('GET', '/api/queue?limit=1&offset=1')[1]['jobs'][0]['id'], ids[1])
        status, detail = self.request('GET', f'/api/jobs/{ids[0]}')
        self.assertEqual(status, 200)
        self.assertEqual(detail['tasks'][0]['kind'], 'spring')
        self.assertEqual(detail['status'], 'queued')

    def test_cancel_and_retry_require_origin_and_preserve_original(self):
        _, original = self.request('POST', '/api/jobs', {'part': 'spring'})
        path = f'/api/jobs/{original["id"]}'
        self.assertEqual(self.request('POST', path + '/cancel', {}, origin=False)[0], 403)
        self.assertEqual(self.request('POST', path + '/retry', {})[0], 409)
        self.assertEqual(self.request('POST', path + '/cancel', {'unexpected': True})[0], 400)
        status, cancelled = self.request('POST', path + '/cancel', {})
        self.assertEqual(status, 200)
        self.assertEqual(cancelled['status'], 'cancelled')
        status, retried = self.request('POST', path + '/retry', {})
        self.assertEqual(status, 202)
        self.assertNotEqual(retried['id'], original['id'])
        self.assertEqual(retried['configuration'], original['configuration'])
        self.assertEqual(self.request('GET', path)[1]['status'], 'cancelled')
        self.assertEqual(self.request('GET', '/api/queue?status=cancelled')[1]['total'], 1)

    def test_queue_inputs_and_routes_are_bounded(self):
        for query in ('limit=0', 'limit=1001', 'offset=-1', 'limit=oops', 'status=unknown',
                      'status=active&status=all', 'unknown=1'):
            with self.subTest(query=query):
                self.assertEqual(self.request('GET', '/api/queue?' + query)[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs/missing/cancel', {})[0], 404)
        self.assertEqual(self.request('POST', '/api/jobs/missing/retry', {})[0], 404)
        for path in ('/queue', '/queue/'):
            status, body = self.request('GET', path)
            self.assertEqual(status, 200)
            self.assertIn(b'<html', body)
        self.assertEqual(self.request('GET', '/static/../../out/web/jobs.sqlite3')[0], 404)


if __name__ == '__main__':
    unittest.main()
