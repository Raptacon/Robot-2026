"""HTTP server that receives log files uploaded from the robot."""

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from .analyzer import WpilogAnalyzer
from .callbacks import CallbackRegistry

logger = logging.getLogger("match_monitor")


class LogReceiverHandler(BaseHTTPRequestHandler):
    """Handles POST /upload, POST /match-complete, and GET /status requests."""

    output_dir: Path  # Set by run_server before starting
    callback_registry: CallbackRegistry  # Set by run_server
    analyzer: WpilogAnalyzer  # Set by run_server

    def do_GET(self):
        if self.path == '/status':
            self._send_json(200, {
                'status': 'ready',
                'output_dir': str(self.output_dir),
                'timestamp': datetime.now().isoformat(),
            })
        elif self.path == '/check':
            self._handle_check()
        else:
            self._send_json(404, {'error': 'not found'})

    def _handle_check(self):
        """Return SHA-256 of a stored file so the client can compare."""
        filename = self.headers.get('X-Filename')
        if not filename:
            self._send_json(400, {'error': 'X-Filename header required'})
            return

        filename = Path(filename).name
        sub_dir = self._build_match_dir()
        dest = self.output_dir / sub_dir / filename

        if not dest.exists():
            self._send_json(200, {'exists': False, 'filename': filename})
            return

        sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
        self._send_json(200, {
            'exists': True,
            'filename': filename,
            'sha256': sha256,
            'size': dest.stat().st_size,
        })

    def do_POST(self):
        if self.path == '/match-complete':
            self._handle_match_complete()
            return
        elif self.path != '/upload':
            self._send_json(404, {'error': 'not found'})
            return

        filename = self.headers.get('X-Filename')
        if not filename:
            self._send_json(400, {'error': 'X-Filename header required'})
            return

        # Sanitize filename
        filename = Path(filename).name
        if not filename:
            self._send_json(400, {'error': 'invalid filename'})
            return

        # Build subdirectory from match metadata
        sub_dir = self._build_match_dir()
        dest_dir = self.output_dir / sub_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / filename
        overwrite = self.headers.get('X-Overwrite', '').lower() == 'true'
        if dest.exists() and not overwrite:
            logger.info(f"Duplicate skipped: {sub_dir}/{filename}")
            self._send_json(409, {'error': 'file already exists',
                                  'filename': filename})
            return

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._send_json(400, {'error': 'empty body'})
            return

        part_path = dest.with_suffix(dest.suffix + '.part')
        try:
            start_time = time.monotonic()
            data = self.rfile.read(content_length)
            part_path.write_bytes(data)
            part_path.rename(dest)
            elapsed = time.monotonic() - start_time
            rate_mbps = (len(data) / (1024 * 1024)) / elapsed if elapsed > 0 else 0

            action = "Updated" if overwrite and dest.exists() else "Received"
            msg = (f"{action}: {sub_dir}/{filename} "
                   f"({len(data):,} bytes in {elapsed:.2f}s, {rate_mbps:.1f} MB/s)")
            logger.info(msg)
            print(f"[{datetime.now():%H:%M:%S}] {msg}")

            self._send_json(200, {'status': 'ok', 'filename': filename,
                                  'size': len(data),
                                  'transfer_seconds': round(elapsed, 3)})
        except Exception as e:
            logger.exception(f"Failed to save {filename}")
            if part_path.exists():
                part_path.unlink()
            self._send_json(500, {'error': str(e)})

    def _handle_match_complete(self):
        """Analyze uploaded logs and run callbacks in a background thread."""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._send_json(400, {'error': 'empty body'})
            return

        try:
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {'error': 'invalid JSON'})
            return

        event_name = body.get('event_name', '').strip()
        match_type = body.get('match_type', '').strip()
        match_number = body.get('match_number', '').strip()

        if event_name and match_type and match_number:
            sub_dir = f"{event_name}/{match_type}_{match_number}"
        elif event_name:
            sub_dir = event_name
        else:
            sub_dir = f"unknown/{datetime.now():%Y-%m-%d}"

        match_dir = self.output_dir / sub_dir
        if not match_dir.is_dir():
            self._send_json(404, {'error': 'match directory not found',
                                  'path': sub_dir})
            return

        wpilog_files = list(match_dir.glob('*.wpilog'))
        msg = (f"Match complete: {sub_dir} "
               f"({len(wpilog_files)} .wpilog files)")
        logger.info(msg)
        print(f"[{datetime.now():%H:%M:%S}] {msg}")

        metadata = {
            'event_name': event_name,
            'match_type': match_type,
            'match_number': match_number,
        }

        # Run analysis in background thread so HTTP response is immediate
        analyzer = self.analyzer
        registry = self.callback_registry
        threading.Thread(
            target=_run_analysis,
            args=(analyzer, registry, match_dir, metadata),
            daemon=True,
        ).start()

        self._send_json(200, {
            'status': 'analysis_started',
            'match_dir': sub_dir,
            'wpilog_files': len(wpilog_files),
        })

    def _build_match_dir(self) -> str:
        event_name = self.headers.get('X-Event-Name', '').strip()
        match_type = self.headers.get('X-Match-Type', '').strip()
        match_number = self.headers.get('X-Match-Number', '').strip()

        if event_name and match_type and match_number:
            return f"{event_name}/{match_type}_{match_number}"
        elif event_name:
            return event_name
        else:
            return f"unknown/{datetime.now():%Y-%m-%d}"

    def _send_json(self, status_code: int, body: dict):
        payload = json.dumps(body).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


def _run_analysis(analyzer: WpilogAnalyzer, registry: CallbackRegistry,
                   match_dir: Path, metadata: dict) -> None:
    """Background worker: analyze .wpilog files and run callbacks."""
    try:
        stats = analyzer.analyze_directory(match_dir)
        msg = (f"Analysis complete: {match_dir.name} — "
               f"brownouts={stats.brownout_count}, "
               f"disconnects={stats.disconnect_count}, "
               f"voltage={stats.avg_voltage}")
        logger.info(msg)
        print(f"[{datetime.now():%H:%M:%S}] {msg}")
        registry.run_all(match_dir, metadata, stats)
    except Exception:
        logger.exception(f"Analysis failed for {match_dir}")


def run_server(bind: str, port: int, output_dir: str = None):
    """Start the log receiver HTTP server."""
    if output_dir is None:
        output_dir = os.path.join(Path.home(), 'Documents', 'robotlogs')

    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    # Set up file logging under <output_dir>/server/
    log_dir = out_path / 'server'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"match_monitor_{datetime.now():%Y%m%d_%H%M%S}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

    LogReceiverHandler.output_dir = out_path
    LogReceiverHandler.analyzer = WpilogAnalyzer()

    registry = CallbackRegistry()
    from .callbacks import JsonSummaryCallback
    registry.register(JsonSummaryCallback())
    LogReceiverHandler.callback_registry = registry

    server = HTTPServer((bind, port), LogReceiverHandler)
    logger.info(f"Match Monitor started on {bind}:{port}, saving to {out_path}")
    print(f"Match Monitor - Log Receiver")
    print(f"Listening on {bind}:{port}")
    print(f"Saving files to {out_path}")
    print(f"Server log: {log_file}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        print("\nShutting down")
        server.shutdown()
