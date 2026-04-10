"""
Camera visualizer server.

Reads constants/robot_geometry.py (single source of truth), injects the
data as JSON into the HTML page, and serves it on localhost.

Usage:
    python -m host.camera_visualizer.serve          # from project root
    python host/camera_visualizer/serve.py           # also works
"""

import http.server
import importlib
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

PORT = 8070

_IN = 0.0254


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


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            # Rebuild every request so geometry edits are picked up
            # without restarting the server — just refresh the browser.
            page = build_page()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store')
            self.send_header('Content-Length', str(len(page)))
            self.end_headers()
            self.write(page)
        elif self.path == '/api/config':
            data = build_config_json().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.write(data)
        else:
            self.send_error(404)

    def write(self, data):
        self.wfile.write(data)

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
