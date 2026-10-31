"""Local-only browser UI + JSON API. Never expose this development server publicly."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .service import ProjectStore, list_samples
from .quality import capabilities_snapshot

STATIC = Path(__file__).parent / 'static'
MAX_BODY = 3 * 1024 * 1024


class StudioServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address, handler_class=None):
        super().__init__(address, handler_class or StudioHandler)
        self.projects = ProjectStore()


class StudioHandler(BaseHTTPRequestHandler):
    server: StudioServer

    def respond(self, status, body: bytes, media='application/json; charset=utf-8', *, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', media)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'no-referrer')
        default_headers = {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'none'"}
        default_headers.update(headers or {})
        for key, value in default_headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def json_response(self, status, value):
        self.respond(status, json.dumps(value, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path in {'/', '/index.html'}:
            return self._static('index.html')
        if path.startswith('/static/'):
            return self._static(path[len('/static/'):])
        if path == '/api/capabilities':
            return self.json_response(200, capabilities_snapshot())
        if path == '/api/samples':
            return self.json_response(200, {'samples': list_samples()})
        if path.startswith('/api/preview/'):
            tokens = path.split('/')[3:]
            if len(tokens) < 3 or tokens[1] not in {'client', 'structural'}:
                return self.json_response(404, {'error': 'Unknown preview'})
            project, mode, relative = tokens[0], tokens[1], '/'.join(tokens[2:])
            if '..' in Path(relative).parts or not relative or relative.startswith('/'):
                return self.json_response(404, {'error': 'Unknown preview file'})
            try:
                data = self.server.projects.output_file(project, mode, relative)
            except KeyError:
                return self.json_response(404, {'error': 'Preview not generated'})
            mime = {'html': 'text/html; charset=utf-8', 'css': 'text/css; charset=utf-8', 'svg': 'image/svg+xml', 'json': 'application/json'}.get(Path(relative).suffix.lstrip('.'), 'application/octet-stream')
            # A sandboxed iframe prevents source fragments from running scripts.
            return self.respond(200, data, mime, headers={'Content-Security-Policy': "default-src 'none'; style-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'"})
        if path.startswith('/api/export/'):
            tokens = path.split('/')
            if len(tokens) != 5 or tokens[4] not in {'client', 'structural'}:
                return self.json_response(404, {'error': 'Unknown export'})
            try:
                data = self.server.projects.export(tokens[3], tokens[4])
            except KeyError as exc:
                return self.json_response(404, {'error': str(exc)})
            return self.respond(200, data, 'application/zip', headers={'Content-Disposition': f'attachment; filename="migration-{tokens[4]}.zip"'})
        return self.json_response(404, {'error': 'Not found'})

    def _static(self, file_name):
        if file_name not in {'index.html', 'styles.css', 'app.js'}:
            return self.json_response(404, {'error': 'Unknown static resource'})
        mime = {'index.html':'text/html; charset=utf-8','styles.css':'text/css; charset=utf-8','app.js':'text/javascript; charset=utf-8'}[file_name]
        return self.respond(200, (STATIC / file_name).read_bytes(), mime)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in {'/api/analyze', '/api/render', '/api/css-workbench'}:
            return self.json_response(404, {'error': 'Not found'})
        if not self.headers.get('Content-Type', '').lower().startswith('application/json'):
            return self.json_response(415, {'error': 'Expected application/json'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > MAX_BODY:
                return self.json_response(413, {'error': 'JSON request must be between 1 byte and 3 MB'})
            req = json.loads(self.rfile.read(size))
            if not isinstance(req, dict):
                raise ValueError('Expected a JSON object')
            if path == '/api/css-workbench':
                project_id = req.get('projectId')
                css = req.get('css')
                if not isinstance(project_id, str) or not isinstance(css, str):
                    raise ValueError('Expected projectId and CSS text')
                result = self.server.projects.review_stylesheet(project_id, req.get('mode', 'client'), css, selector_map=req.get('selectorMap'))
            elif path == '/api/analyze':
                result = self.server.projects.analyze(sample_id=req.get('sampleId'), source=req.get('source'))
            else:
                project_id = req.get('projectId')
                if not isinstance(project_id, str):
                    raise ValueError('Missing projectId')
                result = self.server.projects.render(project_id, mode=req.get('mode', 'client'), profile=req.get('profile'))
            return self.json_response(200, result)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.json_response(400, {'error': str(exc)[:500]})
        except KeyError as exc:
            return self.json_response(404, {'error': str(exc)[:500]})


def serve(host='127.0.0.1', port=8765):
    if host not in {'127.0.0.1', 'localhost'}:
        raise ValueError('MVP local server must bind to loopback only')
    with StudioServer((host, port)) as server:
        print(f'Migration Studio running at http://127.0.0.1:{server.server_port}')
        print('Local-only development server. Press Ctrl+C to stop.')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
