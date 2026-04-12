"""
Camera visualizer HTTP server.

Thin routing layer — business logic lives in routes/ and field_cache.py.

Usage:
    python -m host.camera_visualizer.serve
    python host/camera_visualizer/serve.py
"""

import http.server
import json
import os
import signal
import sys
import threading
import webbrowser

# Resolve project root (two levels up from this file)
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from host.camera_visualizer.field_cache import FieldCache  # noqa: E402
from host.camera_visualizer.routes import (  # noqa: E402
    cad, config, fields, points,
)

PORT = 8070
CAD_DIR = os.path.join(PROJECT_ROOT, 'cad')
CACHE_DIR = os.path.join(PROJECT_ROOT, 'cache', 'fields')
BUNDLE_CACHE = os.path.join(PROJECT_ROOT, 'cache', 'frc_assets.zip')
POINTS_DIR = os.path.join(PROJECT_ROOT, 'data', 'field_points')

field_cache = FieldCache(CACHE_DIR, BUNDLE_CACHE)


class Handler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path

        # ── Page ──────────────────────────────────────────────────
        if path in ('/', '/index.html'):
            page = config.build_page(HERE)
            self._respond(200, 'text/html; charset=utf-8', page,
                          cache='no-cache, no-store')

        # ── API: robot config ─────────────────────────────────────
        elif path == '/api/config':
            self._respond_json(config.build_config_json())

        # ── API: field list ───────────────────────────────────────
        elif path == '/api/field-list':
            self._respond_json(json.dumps(field_cache.get_field_list()))

        # ── API: field tags (from robotpy_apriltag) ───────────────
        elif path == '/api/field-tags':
            self._respond_json(json.dumps(fields.get_field_tags()))

        # ── API: field GLB model ──────────────────────────────────
        elif path.startswith('/api/field/') and path.endswith('.glb'):
            field_id = path[len('/api/field/'):-4]
            _, glb = field_cache.extract_field(field_id)
            if glb is None:
                self.send_error(404, f'Field {field_id} not found')
                return
            self._respond(200, 'model/gltf-binary', glb,
                          cache='public, max-age=86400')

        # ── API: field config JSON ────────────────────────────────
        elif path.startswith('/api/field/') and path.endswith('.json'):
            field_id = path[len('/api/field/'):-5]
            cfg, _ = field_cache.extract_field(field_id)
            if cfg is None:
                self.send_error(404, f'Field {field_id} config not found')
                return
            self._respond_json(json.dumps(cfg))

        # ── API: saved points ─────────────────────────────────────
        elif path == '/api/points/list':
            self._respond_json(json.dumps(points.list_point_sets(POINTS_DIR)))

        elif path == '/api/points':
            set_name = self._query_param('set', 'default')
            self._respond_json(points.load_points(POINTS_DIR, set_name))

        # ── API: CAD model list ───────────────────────────────────
        elif path == '/api/cad-models':
            self._respond_json(json.dumps(cad.list_cad_models(CAD_DIR)))

        # ── Static: CAD files ─────────────────────────────────────
        elif path.startswith('/cad/'):
            data, mime = cad.serve_cad_file(CAD_DIR, path[5:])
            if data is None:
                self.send_error(404)
                return
            self._respond(200, mime, data, cache='public, max-age=3600')

        # ── Static: JS modules ────────────────────────────────────
        elif path.endswith('.js') and '/' not in path[1:]:
            fpath = os.path.join(HERE, path[1:])
            if not os.path.isfile(fpath):
                self.send_error(404)
                return
            with open(fpath, 'rb') as f:
                data = f.read()
            self._respond(200, 'application/javascript', data,
                          cache='no-cache, no-store')

        else:
            self.send_error(404)

    def do_POST(self):
        from urllib.parse import urlparse
        post_path = urlparse(self.path).path
        if post_path == '/api/points':
            set_name = self._query_param('set', 'default')
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            points.save_points(POINTS_DIR, set_name, body)
            self._respond_json('{"ok":true}')
        else:
            self.send_error(404)

    def _respond(self, code, content_type, data, cache=None):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        if cache:
            self.send_header('Cache-Control', cache)
        self.end_headers()
        self.wfile.write(data)

    def _query_param(self, key, default=''):
        """Extract a query parameter from the request path."""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        return params.get(key, [default])[0]

    def _respond_json(self, json_str):
        data = json_str.encode('utf-8') if isinstance(json_str, str) else json_str
        self._respond(200, 'application/json', data, cache='no-cache')

    def log_message(self, format, *args):
        pass


def main():
    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(('127.0.0.1', PORT), Handler)
    url = f'http://127.0.0.1:{PORT}'
    print(f'Camera visualizer running at {url}')
    print('Press Ctrl+C to stop.')

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    webbrowser.open(url)

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
    print('\nShutting down.')
    server.server_close()


if __name__ == '__main__':
    main()
