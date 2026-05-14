"""HTTP server for the controller web editor.

stdlib ``http.server`` is sufficient: this is a localhost dev tool, not a
production service.  Three concerns are wired together:

* Serve files out of ``static/`` (the built SPA, or a placeholder page).
* Expose a small JSON API under ``/api/`` for config I/O.
* Keep all filesystem access through :mod:`paths.safe_resolve`.

Run with ``python -m host.controller_web_editor``.
"""

from __future__ import annotations

import argparse
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .build import maybe_build_spa
from .paths import PathNotAllowedError, list_yaml_configs, safe_resolve
from .routes.config import load_as_json, save_from_json
from .routes.export import ExportRequestError, export_from_yaml
from .routes.hitboxes import (
    LayoutNotAllowedError,
    list_layouts,
    load_layout,
    save_layout,
)
from .routes.prefs import load_prefs, save_prefs


log = logging.getLogger("controller_web_editor")

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Shown in the browser when ``static/index.html`` is missing -- e.g. a
# bare checkout without Node and without the committed bundle.  Plain
# string so we don't need a template file on disk.
_MISSING_BUILD_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Controller Editor: build missing</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto;
       padding: 0 1rem; color: #222; }
h1 { font-size: 1.4rem; }
code, pre { background: #f3f3f3; padding: 0.1rem 0.4rem; border-radius: 4px;
            font-family: Consolas, "SF Mono", monospace; }
pre { padding: 0.6rem 0.8rem; overflow-x: auto; }
.tip { color: #555; font-size: 0.9em; margin-top: 1.5rem; }
</style></head><body>
<h1>The SPA isn't built yet</h1>
<p>The server is running but <code>static/index.html</code> doesn't exist,
so there's nothing to serve at <code>/</code>.</p>
<p>Build the frontend with:</p>
<pre>cd host/controller_web_editor/web
npm install
npm run build</pre>
<p>Then reload this page.  After that, the server will rebuild
automatically whenever you edit files under <code>web/src/</code>.</p>
<p class="tip">If you don't have Node installed, grab it from
<a href="https://nodejs.org">nodejs.org</a> (LTS is fine).  Or pull a
fresh checkout -- the compiled bundle is checked in.</p>
</body></html>
"""

# MIME types we explicitly recognise.  Anything else falls back to octet-stream.
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".map": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    # Quieter access log; we'll route through logging instead of stderr.
    def log_message(self, fmt, *args):  # noqa: N802 (stdlib name)
        log.info("%s - %s", self.address_string(), fmt % args)

    # --- response helpers ---

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _send_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            return
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type", _MIME.get(path.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # --- request entry points ---

    def do_GET(self):  # noqa: N802 (stdlib name)
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)

        if parts.path == "/api/configs":
            self._send_json(HTTPStatus.OK, {"configs": list_yaml_configs()})
            return

        if parts.path == "/api/config":
            path_param = (query.get("path") or [""])[0]
            try:
                resolved = safe_resolve(path_param)
            except PathNotAllowedError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if not resolved.is_file():
                self._send_error_json(
                    HTTPStatus.NOT_FOUND, f"no such file: {path_param}")
                return
            try:
                self._send_json(HTTPStatus.OK, load_as_json(resolved))
            except Exception as exc:
                log.exception("load failed for %s", resolved)
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return

        if parts.path == "/api/hitboxes":
            layout = (query.get("layout") or ["xbox"])[0]
            try:
                self._send_json(HTTPStatus.OK, load_layout(layout))
            except LayoutNotAllowedError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            except FileNotFoundError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            except Exception as exc:
                log.exception("hitboxes load failed for %s", layout)
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return

        if parts.path == "/api/hitboxes/layouts":
            self._send_json(HTTPStatus.OK, {"layouts": list_layouts()})
            return

        if parts.path == "/api/prefs":
            self._send_json(HTTPStatus.OK, load_prefs())
            return

        if parts.path == "/api/export":
            path_param = (query.get("path") or [""])[0]
            orientation = (query.get("orientation") or ["landscape"])[0]
            fmt = (query.get("format") or ["pdf"])[0]
            hide_raw = (query.get("hide_unassigned") or ["0"])[0].lower()
            hide_unassigned = hide_raw in ("1", "true", "yes", "on")
            try:
                resolved = safe_resolve(path_param)
            except PathNotAllowedError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if not resolved.is_file():
                self._send_error_json(
                    HTTPStatus.NOT_FOUND, f"no such file: {path_param}")
                return
            try:
                data, content_type, filename = export_from_yaml(
                    resolved, orientation, fmt, hide_unassigned)
            except ExportRequestError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            except ValueError as exc:
                # No controllers, multi-page PNG, etc.
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            except Exception as exc:
                log.exception("export failed for %s", resolved)
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        # Static files.  Default route serves index.html.
        rel = parts.path.lstrip("/") or "index.html"
        target = (STATIC_DIR / rel).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._send_error_json(HTTPStatus.FORBIDDEN, "outside static root")
            return
        if not target.is_file():
            # SPA fallback — anything unknown returns index.html so the
            # frontend router can decide.
            target = STATIC_DIR / "index.html"
            if not target.is_file():
                # Friendly explainer when nobody has built the bundle.
                body = _MISSING_BUILD_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
        self._send_file(target)

    def do_POST(self):  # noqa: N802 (stdlib name)
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)

        if parts.path == "/api/config":
            path_param = (query.get("path") or [""])[0]
            try:
                resolved = safe_resolve(path_param)
            except PathNotAllowedError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST, f"invalid JSON: {exc}")
                return
            try:
                save_from_json(resolved, payload)
            except Exception as exc:
                log.exception("save failed for %s", resolved)
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                return
            self._send_json(HTTPStatus.OK, {"saved": path_param})
            return

        if parts.path == "/api/hitboxes":
            layout = (query.get("layout") or ["xbox"])[0]
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST, f"invalid JSON: {exc}")
                return
            try:
                save_layout(layout, payload)
            except LayoutNotAllowedError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            except Exception as exc:
                log.exception("hitboxes save failed for %s", layout)
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                return
            self._send_json(HTTPStatus.OK, {"saved": layout})
            return

        if parts.path == "/api/prefs":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST, f"invalid JSON: {exc}")
                return
            if not isinstance(payload, dict):
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST, "payload must be a JSON object")
                return
            try:
                updated = save_prefs(payload)
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            except Exception as exc:
                log.exception("prefs save failed")
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                return
            self._send_json(HTTPStatus.OK, updated)
            return

        self._send_error_json(HTTPStatus.NOT_FOUND, parts.path)


def run(host: str = "127.0.0.1", port: int = 8071) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Auto-build the SPA if web/src/ is newer than static/.  Best-effort;
    # skipped silently when Node isn't installed or
    # CONTROLLER_WEB_EDITOR_SKIP_BUILD is set.
    status = maybe_build_spa()
    log.info("spa build: %s", status)
    server = ThreadingHTTPServer((host, port), Handler)
    log.info("serving on http://%s:%d (static=%s)", host, port, STATIC_DIR)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8071)
    args = parser.parse_args(argv)
    run(args.host, args.port)
    return 0
