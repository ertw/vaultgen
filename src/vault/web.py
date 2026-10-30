"""Vault generator: loopback HTTP API and local browser assets."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlsplit, parse_qs

from .generator import Configuration, catalog, parse_configuration
from .project import PROJECT_ROOT
from ._build import git_provenance
# Preserve the existing imports used by local integrations.
from .web_builds import BuildFiles, freshness
from .web_jobs import Jobs


STATIC = Path(__file__).with_name('static')


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
                if path == '/api/labels/config':
                    from .label_config import label_catalog
                    return self.send(200, label_catalog())
                if path == '/api/gridfinity/config':
                    from .bin_config import bin_catalog
                    return self.send(200, bin_catalog())
                if path == '/api/assembly':
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if any(len(values) != 1 for values in query.values()):
                        return self.send(400, {'error': 'Duplicate assembly parameters'})
                    try:
                        values = {key: value[0] for key, value in query.items()}
                        for key in ('depth_units', 'height_units', 'drawer_columns', 'drawer_rows'):
                            if key in values:
                                values[key] = int(values[key])
                        for key in ('box_floor', 'module_rear', 'pattern_pitch', 'pattern_depth', 'pattern_line_width', 'nozzle_size'):
                            if key in values:
                                values[key] = float(values[key])
                        if 'wall_perimeters' in values and values['wall_perimeters'] != 'full':
                            values['wall_perimeters'] = int(values['wall_perimeters'])
                        if 'facade_floor' in values and values['facade_floor'] != 'default':
                            values['facade_floor'] = float(values['facade_floor'])
                        values.setdefault('part', 'set')
                        config = Configuration.parse_request(values)
                        if config.part != 'set':
                            raise ValueError('Assembly previews require a complete set')
                    except (ValueError, TypeError) as error:
                        return self.send(400, {'error': str(error)})
                    return self.send(200, jobs.files.assembly(config))
                if path == '/api/builds':
                    repository = git_provenance(PROJECT_ROOT)
                    return self.send(200, {'builds': jobs.files.history(repository), 'repository': repository})
                if path.startswith('/api/builds/'):
                    pieces = path.strip('/').split('/')
                    if len(pieces) != 4 or pieces[3] != 'bundle.zip':
                        raise FileNotFoundError('Unknown endpoint')
                    build = jobs.files.describe(pieces[2])
                    return self.build_bundle([build], build['configuration'], f'vault-{build["id"]}.zip')
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
                relative = ('index.html' if path == '/' else 'labels.html'
                            if path in ('/labels', '/labels/') else 'gridfinity.html'
                            if path in ('/gridfinity', '/gridfinity/') else path.removeprefix('/static/'))
                file = STATIC / relative
                if (path not in ('/', '/labels', '/labels/', '/gridfinity', '/gridfinity/') and not path.startswith('/static/')) or not file.resolve().is_relative_to(STATIC.resolve()):
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
            return self.build_bundle(job['builds'], job['configuration'], f'vault-{job_id[:8]}.zip')

        def build_bundle(self, builds, configuration, filename):
            with tempfile.TemporaryFile() as archive:
                jobs.files.write_bundle(archive, builds, configuration)
                size = archive.tell()
                archive.seek(0)
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Length', str(size))
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
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
                if not 0 < length <= 8192:
                    return self.send(413, {'error': 'Request must contain at most 8192 bytes'})
                value = json.loads(self.rfile.read(length))
                config = parse_configuration(value, new_request=True)
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
