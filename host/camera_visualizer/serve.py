"""
Camera visualizer server.

Reads constants/robot_geometry.py (single source of truth), injects the
data as JSON into the HTML page, and serves it on localhost.

Serves field models from AdvantageScope's GitHub-hosted asset bundle,
caching them locally in cache/fields/.

Usage:
    python -m host.camera_visualizer.serve          # from project root
    python host/camera_visualizer/serve.py           # also works
"""

import http.server
import importlib
import io
import json
import os
import signal
import sys
import threading
import urllib.request
import webbrowser
import zipfile

# Resolve project root (two levels up from this file)
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

PORT = 8070
CACHE_DIR = os.path.join(PROJECT_ROOT, 'cache', 'fields')
POINTS_FILE = os.path.join(PROJECT_ROOT, 'data', 'field_points.json')
BUNDLE_URL = (
    'https://github.com/Mechanical-Advantage/AdvantageScopeAssets'
    '/releases/download/bundles-v1/AllAssetsDefaultFRC.zip'
)
BUNDLE_CACHE = os.path.join(PROJECT_ROOT, 'cache', 'frc_assets.zip')

_IN = 0.0254

# Curated field list — name maps to zip entry in the bundle
FIELD_LIST = [
    {
        'id': 'robot-view',
        'name': 'Robot View',
        'description': 'Robot at origin with AprilTag ring',
        'type': 'builtin',
    },
    {
        'id': '2026-field',
        'name': '2026 Field',
        'description': '2026 FRC Rebuilt field',
        'zipEntry': 'Field3d_2026FRCFieldV1.zip',
        'type': 'field',
    },
    {
        'id': '2025-welded',
        'name': '2025 Field (Welded)',
        'description': '2025 FRC field, welded variant',
        'zipEntry': 'Field3d_2025FRCFieldWeldedV2.zip',
        'type': 'field',
    },
    {
        'id': '2025-andymark',
        'name': '2025 Field (AndyMark)',
        'description': '2025 FRC field, AndyMark variant',
        'zipEntry': 'Field3d_2025FRCFieldAndyMarkV2.zip',
        'type': 'field',
    },
    {
        'id': '2024-field',
        'name': '2024 Field',
        'description': '2024 FRC field',
        'zipEntry': 'Field3d_2024FRCFieldV3.zip',
        'type': 'field',
    },
    {
        'id': 'cat-box',
        'name': 'Cat Box',
        'description': 'Meow',
        'type': 'builtin',
    },
]


def _reload_geometry():
    """Re-import robot_geometry so edits are picked up on browser refresh."""
    import constants.robot_geometry as geo
    importlib.reload(geo)
    return geo


def build_config_json() -> str:
    """Build the JSON config blob that gets injected into the HTML."""
    geo = _reload_geometry()
    config = {
        "robot_frame": {
            "width_inches": round(geo.ROBOT_WIDTH_M / _IN, 2),
            "length_inches": round(geo.ROBOT_LENGTH_M / _IN, 2),
            "width_meters": round(geo.ROBOT_WIDTH_M, 4),
            "length_meters": round(geo.ROBOT_LENGTH_M, 4),
        },
        "cameras": [cam.to_dict() for cam in geo.CAMERAS],
        "mechanisms": [mech.to_dict() for mech in geo.MECHANISMS],
    }
    return json.dumps(config, indent=2)


def build_page() -> bytes:
    """Read index.html and inject the config JSON."""
    html_path = os.path.join(HERE, 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    config_json = build_config_json()
    inject = f'<script>window.__ROBOT_CONFIG__ = {config_json};</script>\n'
    html = html.replace(
        '<script type="module">',
        inject + '<script type="module">',
        1,
    )
    return html.encode('utf-8')


def _ensure_bundle():
    """Download the AdvantageScope asset bundle if not cached."""
    if os.path.isfile(BUNDLE_CACHE):
        return True
    os.makedirs(os.path.dirname(BUNDLE_CACHE), exist_ok=True)
    try:
        print(f'Downloading field assets from {BUNDLE_URL}...')
        urllib.request.urlretrieve(BUNDLE_URL, BUNDLE_CACHE)
        print(f'Downloaded to {BUNDLE_CACHE}')
        return True
    except Exception as e:
        print(f'Failed to download assets: {e}')
        return False


def _extract_field(field_id: str):
    """Extract a field's model.glb and config.json from the bundle.
    Returns (config_dict, glb_bytes) or (None, None) on failure.
    """
    field_info = next((f for f in FIELD_LIST if f['id'] == field_id), None)
    if not field_info or 'zipEntry' not in field_info:
        return None, None

    # Check local cache first
    cache_dir = os.path.join(CACHE_DIR, field_id)
    glb_path = os.path.join(cache_dir, 'model.glb')
    config_path = os.path.join(cache_dir, 'config.json')

    if os.path.isfile(glb_path) and os.path.isfile(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        with open(glb_path, 'rb') as f:
            glb = f.read()
        return config, glb

    # Extract from bundle
    if not _ensure_bundle():
        return None, None

    try:
        outer = zipfile.ZipFile(BUNDLE_CACHE)
        inner_data = outer.read(field_info['zipEntry'])
        inner = zipfile.ZipFile(io.BytesIO(inner_data))

        config = json.loads(inner.read('config.json'))
        glb = inner.read('model.glb')

        # Cache locally
        os.makedirs(cache_dir, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f)
        with open(glb_path, 'wb') as f:
            f.write(glb)

        return config, glb
    except Exception as e:
        print(f'Failed to extract field {field_id}: {e}')
        return None, None


def _get_field_tags():
    """Get AprilTag positions from robotpy_apriltag field layout."""
    try:
        from robotpy_apriltag import AprilTagField, AprilTagFieldLayout
        layout = AprilTagFieldLayout.loadField(AprilTagField.kDefaultField)
        tags = []
        for tag_id in range(1, 50):
            pose = layout.getTagPose(tag_id)
            if pose is None:
                continue
            t = pose.translation()
            r = pose.rotation()
            tags.append({
                'id': tag_id,
                'x': round(t.X(), 4),
                'y': round(t.Y(), 4),
                'z': round(t.Z(), 4),
                'roll_deg': round(r.x_degrees, 1),
                'pitch_deg': round(r.y_degrees, 1),
                'yaw_deg': round(r.z_degrees, 1),
            })
        return {
            'field_length': round(layout.getFieldLength(), 4),
            'field_width': round(layout.getFieldWidth(), 4),
            'tags': tags,
        }
    except Exception as e:
        return {'error': str(e), 'tags': []}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            page = build_page()
            self._respond(200, 'text/html; charset=utf-8', page,
                          cache='no-cache, no-store')

        elif self.path == '/api/config':
            self._respond_json(build_config_json())

        elif self.path == '/api/field-list':
            self._respond_json(json.dumps(FIELD_LIST))

        elif self.path == '/api/field-tags':
            self._respond_json(json.dumps(_get_field_tags()))

        elif self.path.startswith('/api/field/') and self.path.endswith('.glb'):
            field_id = self.path[len('/api/field/'):-4]
            config, glb = _extract_field(field_id)
            if glb is None:
                self.send_error(404, f'Field {field_id} not found')
                return
            self._respond(200, 'model/gltf-binary', glb,
                          cache='public, max-age=86400')

        elif self.path.startswith('/api/field/') and self.path.endswith('.json'):
            field_id = self.path[len('/api/field/'):-5]
            config, _ = _extract_field(field_id)
            if config is None:
                self.send_error(404, f'Field {field_id} config not found')
                return
            self._respond_json(json.dumps(config))

        elif self.path == '/api/points':
            if os.path.isfile(POINTS_FILE):
                with open(POINTS_FILE, 'r') as f:
                    self._respond_json(f.read())
            else:
                self._respond_json('{"points":[]}')

        elif self.path == '/api/cad-models':
            cad_dir = os.path.join(PROJECT_ROOT, 'cad')
            models = []
            if os.path.isdir(cad_dir):
                for fname in sorted(os.listdir(cad_dir)):
                    if fname.lower().endswith(('.glb', '.gltf')):
                        size = os.path.getsize(
                            os.path.join(cad_dir, fname)
                        )
                        models.append({
                            'name': fname,
                            'url': f'/cad/{fname}',
                            'size': size,
                        })
            self._respond_json(json.dumps(models))

        elif self.path.startswith('/cad/'):
            fname = os.path.basename(self.path[5:])
            if not fname.lower().endswith(('.glb', '.gltf', '.bin')):
                self.send_error(403)
                return
            fpath = os.path.join(PROJECT_ROOT, 'cad', fname)
            if not os.path.isfile(fpath):
                self.send_error(404)
                return
            with open(fpath, 'rb') as f:
                data = f.read()
            mime = {
                '.glb': 'model/gltf-binary',
                '.gltf': 'model/gltf+json',
                '.bin': 'application/octet-stream',
            }.get(os.path.splitext(fname)[1].lower(), 'application/octet-stream')
            self._respond(200, mime, data, cache='public, max-age=3600')

        elif self.path.endswith('.js') and '/' not in self.path[1:]:
            # Serve JS modules from the visualizer directory
            fpath = os.path.join(HERE, self.path[1:])
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
        if self.path == '/api/points':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            os.makedirs(os.path.dirname(POINTS_FILE), exist_ok=True)
            with open(POINTS_FILE, 'wb') as f:
                f.write(body)
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
