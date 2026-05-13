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

from .paths import PathNotAllowedError, list_yaml_configs, safe_resolve
from .routes.config import load_as_json, save_from_json
from .routes.hitboxes import (
    LayoutNotAllowedError,
    list_layouts,
    load_layout,
    save_layout,
)


log = logging.getLogger("controller_web_editor")

STATIC_DIR = Path(__file__).resolve().parent / "static"

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
                self._send_error_json(HTTPStatus.NOT_FOUND, parts.path)
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

        self._send_error_json(HTTPStatus.NOT_FOUND, parts.path)


def run(host: str = "127.0.0.1", port: int = 8071) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
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
