"""HTTP server that receives log files uploaded from the robot."""

import hashlib
import json
import logging
import os
import threading
import time
import zlib
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from .analyzer import WpilogAnalyzer
from .callbacks import CallbackRegistry
from .connector import RobotConnector
from .ds_log_reader import collect_for_match
from .match_data_client import MatchDataClient

logger = logging.getLogger("match_monitor")

LOG_LEVELS = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
}
LOG_DISABLED = logging.CRITICAL + 1


class LogReceiverHandler(BaseHTTPRequestHandler):
    """Handles POST /upload, GET /check, and GET /status requests."""

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
        if self.path != '/upload':
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
            raw_data = self.rfile.read(content_length)
            compressed_size = len(raw_data)

            # Decompress if client sent compressed data
            content_encoding = self.headers.get('Content-Encoding', '')
            if content_encoding == 'deflate':
                data = zlib.decompress(raw_data)
                uncompressed_size = len(data)
            else:
                data = raw_data
                uncompressed_size = len(data)

            part_path.write_bytes(data)
            part_path.rename(dest)
            elapsed = time.monotonic() - start_time
            rate_mbps = (compressed_size / (1024 * 1024)) / elapsed if elapsed > 0 else 0

            action = "Updated" if overwrite and dest.exists() else "Received"
            if content_encoding == 'deflate':
                savings = (1 - compressed_size / uncompressed_size) * 100 if uncompressed_size else 0
                compressed_mb = compressed_size / (1024 * 1024)
                uncompressed_mb = uncompressed_size / (1024 * 1024)
                msg = (f"{action}: {sub_dir}/{filename} "
                       f"({compressed_mb:.1f} MB compressed -> {uncompressed_mb:.1f} MB, "
                       f"{savings:.0f}% savings, {elapsed:.2f}s, {rate_mbps:.1f} MB/s)")
            else:
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
                   match_dir: Path, metadata: dict,
                   match_client: 'MatchDataClient') -> None:
    """Background worker: analyze .wpilog files, collect DS logs, fetch match data, run callbacks."""
    try:
        stats = analyzer.analyze_directory(match_dir)

        # Collect and correlate DS log files using the wpilog wall clock start
        match_time = stats.wpilog_wall_start or datetime.now()
        try:
            stats.ds_log = collect_for_match(match_time, match_dir)
            if stats.ds_log.copied_files:
                logger.info(f"DS logs collected: {', '.join(stats.ds_log.copied_files)}")
        except Exception:
            logger.exception("DS log collection failed (non-fatal)")

        # Fetch official match data from TBA / FRC Events API
        match_result = None
        event_stats = None
        if match_client.configured:
            event_name = metadata.get('event_name', '').strip()
            match_number_str = metadata.get('match_number', '').strip()
            match_type = metadata.get('match_type', '').strip().lower()
            if event_name and match_number_str:
                try:
                    level = 'qm' if 'qual' in match_type else \
                            'sf' if 'semi' in match_type else \
                            'f' if 'final' in match_type else 'qm'
                    match_result = match_client.fetch_match(
                        event_name, int(match_number_str), level)
                    event_stats = match_client.fetch_event_stats(event_name)
                    if match_result:
                        logger.info(f"Official result: {match_result.result} "
                                    f"({match_result.our_score}-{match_result.opponent_score})")
                except Exception:
                    logger.exception("Match data fetch failed (non-fatal)")

        msg = (f"Analysis complete: {match_dir.name} — "
               f"brownouts={stats.brownout_count}, "
               f"disconnects={stats.disconnect_count}, "
               f"voltage={stats.avg_voltage}")
        if stats.ds_log and stats.ds_log.avg_packet_loss_pct is not None:
            msg += f", pkt_loss={stats.ds_log.avg_packet_loss_pct}%"
        if match_result:
            msg += f", result={match_result.result} ({match_result.our_score}-{match_result.opponent_score})"
        logger.info(msg)
        print(f"[{datetime.now():%H:%M:%S}] {msg}")
        registry.run_all(match_dir, metadata, stats, match_result, event_stats)
    except Exception:
        logger.exception(f"Analysis failed for {match_dir}")


def _level_name(level: int) -> str:
    """Return a human-readable name for a logging level."""
    if level >= LOG_DISABLED:
        return 'off'
    return logging.getLevelName(level).lower()


def _console_loop(connector: RobotConnector,
                  console_handler: logging.Handler,
                  file_handler: logging.Handler,
                  log_dir: Path,
                  registry: 'CallbackRegistry',
                  discord_holder: list,
                  config_path: Path,
                  repo_root: Path) -> None:
    """Interactive command loop running in a daemon thread."""
    saved_console_level = console_handler.level
    saved_file_level = file_handler.level
    console_off = False
    file_off = False

    def _require_connection() -> bool:
        if not connector.is_connected:
            print("  Not connected to robot")
            return False
        return True

    def _set_console_level(level: int) -> None:
        nonlocal saved_console_level, console_off
        console_handler.setLevel(level)
        saved_console_level = level
        console_off = False
        print(f"  Console log level: {_level_name(level)}")

    def _handle_log(parts: list) -> None:
        nonlocal saved_console_level, saved_file_level, console_off, file_off, file_handler

        if len(parts) == 1:
            # Just "log" — show current state
            c_level = _level_name(console_handler.level)
            f_level = _level_name(file_handler.level)
            c_state = " (off)" if console_off else ""
            f_state = " (off)" if file_off else ""
            print(f"  Console: {c_level}{c_state}")
            print(f"  File:    {f_level}{f_state}")
            return

        arg1 = parts[1].lower()

        # log off — disable console
        if arg1 == 'off':
            saved_console_level = console_handler.level
            console_handler.setLevel(LOG_DISABLED)
            console_off = True
            print("  Console logging disabled")
            return

        # log on — re-enable console
        if arg1 == 'on':
            console_handler.setLevel(saved_console_level)
            console_off = False
            print(f"  Console logging enabled ({_level_name(saved_console_level)})")
            return

        # log rotate
        if arg1 == 'rotate':
            old_file = file_handler.baseFilename
            logger.removeHandler(file_handler)
            file_handler.close()
            new_log_file = log_dir / f"match_monitor_{datetime.now():%Y%m%d_%H%M%S}.log"
            file_handler = logging.FileHandler(new_log_file)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
            ))
            file_handler.setLevel(saved_file_level)
            if not file_off:
                logger.addHandler(file_handler)
            print(f"  Rotated log file: {new_log_file}")
            return

        # log console <level|off|on>
        if arg1 == 'console':
            if len(parts) < 3:
                print(f"  Console: {_level_name(console_handler.level)}")
                return
            arg2 = parts[2].lower()
            if arg2 == 'off':
                saved_console_level = console_handler.level
                console_handler.setLevel(LOG_DISABLED)
                console_off = True
                print("  Console logging disabled")
            elif arg2 == 'on':
                console_handler.setLevel(saved_console_level)
                console_off = False
                print(f"  Console logging enabled ({_level_name(saved_console_level)})")
            elif arg2 in LOG_LEVELS:
                _set_console_level(LOG_LEVELS[arg2])
            else:
                print(f"  Unknown level: {arg2} (use debug, info, warning, error, off, on)")
            return

        # log file <level|off|on>
        if arg1 == 'file':
            if len(parts) < 3:
                print(f"  File: {_level_name(file_handler.level)}")
                return
            arg2 = parts[2].lower()
            if arg2 == 'off':
                saved_file_level = file_handler.level
                if not file_off:
                    logger.removeHandler(file_handler)
                file_off = True
                print("  File logging disabled")
            elif arg2 == 'on':
                if file_off:
                    file_handler.setLevel(saved_file_level)
                    logger.addHandler(file_handler)
                    file_off = False
                print(f"  File logging enabled ({_level_name(saved_file_level)})")
            elif arg2 in LOG_LEVELS:
                file_handler.setLevel(LOG_LEVELS[arg2])
                saved_file_level = LOG_LEVELS[arg2]
                if file_off:
                    logger.addHandler(file_handler)
                    file_off = False
                print(f"  File log level: {arg2}")
            else:
                print(f"  Unknown level: {arg2} (use debug, info, warning, error, off, on)")
            return

        # log <level> — set console level (and re-enable if off)
        if arg1 in LOG_LEVELS:
            _set_console_level(LOG_LEVELS[arg1])
            return

        print(f"  Unknown log command: {arg1}")
        print("  Usage: log [debug|info|warning|error|off|on]")
        print("         log console <level>  |  log file <level>  |  log rotate")

    def _save_config_key(key: str, value) -> None:
        """Read/update/write a single key in match_monitor_config.json."""
        cfg: dict = {}
        if config_path.exists():
            try:
                import json as _json
                cfg = _json.loads(config_path.read_text())
            except Exception:
                pass
        cfg[key] = value
        try:
            import json as _json
            config_path.write_text(_json.dumps(cfg, indent=4) + '\n')
        except Exception as exc:
            print(f"  Warning: could not save config: {exc}")

    def _handle_discord(parts: list) -> None:
        from .discord_notifier import DiscordNotifier

        notifier: DiscordNotifier = discord_holder[0]

        if len(parts) == 1:
            # Show current status
            if notifier and notifier.webhook_url:
                url = notifier.webhook_url
                # Mask middle of token for safety
                masked = url[:45] + '...' + url[-6:] if len(url) > 55 else url
                print(f"  Discord: enabled — {masked}")
            else:
                print("  Discord: disabled (no webhook URL set)")
            return

        arg = parts[1].lower()

        if arg == 'off':
            if notifier:
                notifier.webhook_url = ''
            _save_config_key('discord_webhook_url', '')
            print("  Discord notifications disabled")
            return

        if arg == 'test':
            if not notifier or not notifier.webhook_url:
                print("  No webhook URL configured — use: discord <url>")
                return
            # Send a test message
            try:
                notifier._post({
                    'content': '✅ Match Monitor test message — Discord webhook is working!',
                })
                print("  Test message sent")
            except Exception as exc:
                print(f"  Test failed: {exc}")
            return

        # Treat as a URL
        url = parts[1]  # preserve original case
        if not url.startswith('https://discord.com/api/webhooks/'):
            print("  Expected a Discord webhook URL "
                  "(https://discord.com/api/webhooks/...)")
            return

        if notifier is None:
            notifier = DiscordNotifier(url, repo_root)
            registry.register(notifier)
            discord_holder[0] = notifier
            print(f"  Discord notifier registered")
        else:
            notifier.webhook_url = url
            print(f"  Discord webhook URL updated")

        _save_config_key('discord_webhook_url', url)
        logger.info("Discord webhook URL updated via console")

    def _print_help() -> None:
        print()
        print("  Robot commands (require connection):")
        print("    list              List log files on robot")
        print("    upload            Force robot to start uploading now")
        print("    stop              Stop robot log upload")
        print("    clear-manifest    Clear upload manifest (re-upload all)")
        print()
        print("  Connection:")
        print("    status            Show connection state")
        print("    connect           Resume polling / reconnect")
        print("    disconnect        Close connection and stop polling")
        print()
        print("  Discord:")
        print("    discord           Show current webhook status")
        print("    discord <url>     Set/update webhook URL (saved to config)")
        print("    discord off       Disable Discord notifications")
        print("    discord test      Send a test message")
        print()
        print("  Logging:")
        print("    log               Show current log levels")
        print("    log <level>       Set console log level (debug/info/warning/error)")
        print("    log off|on        Disable/enable console logging")
        print("    log console <lv>  Set console level explicitly")
        print("    log file <lv>     Set file log level")
        print("    log file off|on   Disable/enable file logging")
        print("    log rotate        Rotate to a new log file")
        print()
        print("  help, h, ?          Show this help")
        print()

    while True:
        try:
            line = input("monitor> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ('help', 'h', '?'):
            _print_help()

        elif cmd == 'status':
            info = connector.status_info
            state = info['state']
            print(f"  State:       {state}")
            if info['robot_address']:
                print(f"  Robot:       {info['robot_address']}")
            if info['connected_since'] is not None:
                uptime = time.monotonic() - info['connected_since']
                mins, secs = divmod(int(uptime), 60)
                hrs, mins = divmod(mins, 60)
                print(f"  Uptime:      {hrs}h {mins}m {secs}s")
            print(f"  HTTP port:   {info['http_port']}")
            print(f"  Attempts:    {info['connect_attempts']}")
            print(f"  Polling:     {', '.join(info['poll_addresses'])}")
            if info['last_attempt_addr']:
                print(f"  Last tried:  {info['last_attempt_addr']}")

        elif cmd == 'connect':
            connector.connect()
            print("  Polling resumed")

        elif cmd == 'disconnect':
            connector.disconnect()
            print("  Disconnected, polling stopped")

        elif cmd == 'list':
            if _require_connection():
                connector.send_to_robot({'type': 'LIST_LOGS'})

        elif cmd == 'upload':
            if _require_connection():
                connector.send_to_robot({'type': 'FORCE_UPLOAD'})

        elif cmd == 'stop':
            if _require_connection():
                connector.send_to_robot({'type': 'STOP_UPLOAD'})

        elif cmd == 'clear-manifest':
            if _require_connection():
                connector.send_to_robot({'type': 'CLEAR_MANIFEST'})

        elif cmd == 'discord':
            _handle_discord(parts)

        elif cmd == 'log':
            _handle_log(parts)

        else:
            print(f"  Unknown command: {cmd}. Type 'help' for available commands.")


def run_server(bind: str, port: int, output_dir: str = None, debug: bool = False):
    """Start the log receiver HTTP server."""
    if output_dir is None:
        output_dir = r'C:\Users\Public\Documents\FRC\Log Files\WPILogs'

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

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(message)s', datefmt='%H:%M:%S'
    ))
    logger.addHandler(console_handler)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    LogReceiverHandler.output_dir = out_path
    analyzer = WpilogAnalyzer()
    LogReceiverHandler.analyzer = analyzer

    registry = CallbackRegistry()
    from .callbacks import JsonSummaryCallback
    registry.register(JsonSummaryCallback())
    LogReceiverHandler.callback_registry = registry

    # Load shared config once
    config_path = out_path / 'match_monitor_config.json'
    _cfg: dict = {}
    if config_path.exists():
        try:
            import json as _json
            _cfg = _json.loads(config_path.read_text())
        except Exception:
            logger.warning(f"Failed to read {config_path}")

    # Match data client
    match_client = MatchDataClient(config_path)
    if match_client.configured:
        logger.info("Match data client configured (TBA/FRC Events API)")
    else:
        logger.info("Match data client not configured — skipping official match data "
                    "(add tba_api_key or frc_events credentials to match_monitor_config.json)")

    # Discord notifier
    repo_root = Path(__file__).parent.parent.parent
    discord_url = _cfg.get('discord_webhook_url', '').strip()
    discord_holder: list = [None]  # mutable ref shared with console loop
    if discord_url:
        from .discord_notifier import DiscordNotifier
        discord_holder[0] = DiscordNotifier(discord_url, repo_root)
        registry.register(discord_holder[0])
        logger.info("Discord notifier registered")
    else:
        logger.info("Discord notifier not configured "
                    "(use 'discord <url>' at the monitor prompt, or add to match_monitor_config.json)")

    # Build match directory path from metadata and trigger analysis
    def on_upload_complete(metadata: dict) -> None:
        event_name = metadata.get('event_name', '').strip()
        match_type = metadata.get('match_type', '').strip()
        match_number = metadata.get('match_number', '').strip()

        if event_name and match_type and match_number:
            sub_dir = f"{event_name}/{match_type}_{match_number}"
        elif event_name:
            sub_dir = event_name
        else:
            sub_dir = f"unknown/{datetime.now():%Y-%m-%d}"

        match_dir = out_path / sub_dir
        if not match_dir.is_dir():
            logger.warning(f"Match dir not found for analysis: {sub_dir}")
            return

        threading.Thread(
            target=_run_analysis,
            args=(analyzer, registry, match_dir, metadata, match_client),
            daemon=True,
        ).start()

    # Start TCP connector to poll for roboRIO
    connector = RobotConnector(http_port=port, on_upload_complete=on_upload_complete)
    connector.start()

    # Start interactive console in background thread
    console_thread = threading.Thread(
        target=_console_loop,
        args=(connector, console_handler, file_handler, log_dir,
              registry, discord_holder, config_path, repo_root),
        daemon=True,
    )
    console_thread.start()

    server = HTTPServer((bind, port), LogReceiverHandler)
    logger.info(f"Match Monitor started on {bind}:{port}, saving to {out_path}")
    print(f"Match Monitor - Log Receiver")
    print(f"Listening on {bind}:{port}")
    print(f"Saving files to {out_path}")
    print(f"Server log: {log_file}")
    print(f"TCP connector polling for roboRIO on port 5805")
    print("Type 'help' for commands. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        connector.stop()
        logger.info("Shutting down")
        print("\nShutting down")
        server.shutdown()
