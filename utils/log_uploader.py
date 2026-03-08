"""Non-blocking log file uploader for transferring robot logs to a field PC."""

import hashlib
import http.client
import json
import logging
import threading
import time
import zlib
from pathlib import Path
from typing import Optional, Set, List

import wpilib
from ntcore.util import ntproperty

from utils.control_listener import ControlListener

logger = logging.getLogger(__name__)

LOG_EXTENSIONS = {'.wpilog', '.hoot', '.revlog'}

LOG_DIRS = [
    Path('/media/sda1'),
    Path('/home/lvuser/logs'),
    # Fallback for simulation / Windows dev
    Path.home() / 'Documents' / 'robotlogs',
]

MANIFEST_FILENAME = '.uploaded_manifest'


class LogUploader:
    """Uploads robot log files to a match_monitor receiver via HTTP.

    The host IP and port are discovered via the ControlListener TCP channel.
    Uploads run in a background daemon thread triggered from disabledInit().
    Calling start_upload() when an upload is already running is a safe no-op.
    Call stop_upload() when leaving disabled mode to free bandwidth.
    """

    upload_enabled = ntproperty('/LogUploader/enabled', True,
                                writeDefault=True, persistent=True)
    status = ntproperty('/LogUploader/status', 'idle',
                        writeDefault=True, persistent=False)

    def __init__(self, control_listener: ControlListener) -> None:
        self._control = control_listener
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def start_upload(self) -> None:
        """Begin a non-blocking upload cycle. No-op if already uploading."""
        if not self.upload_enabled:
            self.status = 'disabled'
            return
        if not self._control.is_connected:
            self.status = 'no host connected'
            print("[LogUploader] No host connected, skipping upload")
            return

        host_ip = self._control.host_ip
        http_port = self._control.http_port
        print(f"[LogUploader] start_upload: host={host_ip}:{http_port}")

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.info("Upload already in progress, skipping")
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._upload_worker, daemon=True
            )
            self._thread.start()

    def stop_upload(self) -> None:
        """Signal the upload thread to stop after the current file."""
        self._stop_event.set()

    def stop_and_wait(self, timeout: float = 60) -> None:
        """Stop the upload thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_uploading(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _upload_worker(self) -> None:
        try:
            host_ip = self._control.host_ip
            http_port = self._control.http_port
            if not host_ip or not http_port:
                self.status = 'no host connected'
                return

            self.status = 'scanning'
            log_dirs = self._find_log_dirs()
            print(f"[LogUploader] Found log dirs: {log_dirs}")
            if not log_dirs:
                self.status = 'no log directory found'
                return

            # Gather new files (not in manifest)
            new_files: List[Path] = []
            for log_dir in log_dirs:
                new_files.extend(self._find_new_files(log_dir))

            # Gather previously uploaded files that may have changed
            manifest_files: List[Path] = []
            for log_dir in log_dirs:
                manifest_files.extend(self._find_manifest_files(log_dir))

            print(f"[LogUploader] new={len(new_files)}, manifest={len(manifest_files)}")
            if not new_files and not manifest_files:
                self.status = 'idle (no files)'
                return

            self.status = 'connecting'
            if not self._check_receiver(host_ip, http_port):
                self.status = 'receiver unreachable'
                print("[LogUploader] Receiver unreachable!")
                return

            event_name, match_type, match_number = self._get_match_metadata()

            # Notify host that uploads are starting
            self._control.send_upload_starting(event_name, match_type, match_number)

            uploaded_count = 0
            total = len(new_files) + len(manifest_files)

            # Upload new files first
            for filepath in new_files:
                if self._stop_event.is_set():
                    self.status = f'stopped ({uploaded_count}/{total} uploaded)'
                    return
                # Re-check connection in case host disappeared
                if not self._control.is_connected:
                    self.status = 'host disconnected during upload'
                    return
                self.status = f'uploading {filepath.name}'
                if self._upload_file(filepath, host_ip, http_port,
                                     event_name, match_type, match_number):
                    self._add_to_manifest(filepath)
                    uploaded_count += 1

            # Check previously uploaded files for changes (SHA-256 mismatch)
            for filepath in manifest_files:
                if self._stop_event.is_set():
                    self.status = f'stopped ({uploaded_count}/{total} uploaded)'
                    return
                if not self._control.is_connected:
                    self.status = 'host disconnected during upload'
                    return
                self.status = f'checking {filepath.name}'
                if self._needs_reupload(filepath, host_ip, http_port,
                                        event_name, match_type, match_number):
                    self.status = f're-uploading {filepath.name}'
                    self._upload_file(filepath, host_ip, http_port,
                                      event_name, match_type, match_number,
                                      overwrite=True)
                    uploaded_count += 1

            self.status = f'done ({uploaded_count}/{total} uploaded)'

            # Notify host that uploads are complete
            if not self._stop_event.is_set():
                self._control.send_upload_complete(event_name, match_type, match_number)
        except Exception:
            logger.exception("Upload worker failed")
            self.status = 'error'

    def _find_log_dirs(self) -> List[Path]:
        return [d for d in LOG_DIRS if d.is_dir()]

    def _find_new_files(self, log_dir: Path) -> List[Path]:
        manifest = self._load_manifest(log_dir)
        files = []
        for f in log_dir.iterdir():
            if f.is_file() and f.suffix.lower() in LOG_EXTENSIONS and f.name not in manifest:
                files.append(f)
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files

    def _find_manifest_files(self, log_dir: Path) -> List[Path]:
        """Return files that are in the manifest and still exist on disk."""
        manifest = self._load_manifest(log_dir)
        files = []
        for name in manifest:
            f = log_dir / name
            if f.is_file():
                files.append(f)
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files

    def _add_to_manifest(self, filepath: Path) -> None:
        log_dir = filepath.parent
        manifest = self._load_manifest(log_dir)
        manifest.add(filepath.name)
        self._save_manifest(log_dir, manifest)

    def _load_manifest(self, log_dir: Path) -> Set[str]:
        manifest_path = log_dir / MANIFEST_FILENAME
        if not manifest_path.exists():
            return set()
        try:
            return set(manifest_path.read_text().strip().splitlines())
        except Exception:
            logger.exception("Failed to read upload manifest")
            return set()

    def _save_manifest(self, log_dir: Path, manifest: Set[str]) -> None:
        manifest_path = log_dir / MANIFEST_FILENAME
        try:
            manifest_path.write_text('\n'.join(sorted(manifest)) + '\n')
        except Exception:
            logger.exception("Failed to write upload manifest")

    def _get_match_metadata(self) -> tuple:
        try:
            event_name = wpilib.DriverStation.getEventName()
            match_type = wpilib.DriverStation.getMatchType()
            match_number = wpilib.DriverStation.getMatchNumber()

            type_names = {
                wpilib.DriverStation.MatchType.kNone: '',
                wpilib.DriverStation.MatchType.kPractice: 'practice',
                wpilib.DriverStation.MatchType.kQualification: 'qual',
                wpilib.DriverStation.MatchType.kElimination: 'elim',
            }
            match_type_str = type_names.get(match_type, '')
            return event_name, match_type_str, str(match_number)
        except Exception:
            logger.exception("Failed to get match metadata")
            return '', '', ''

    def _check_receiver(self, host_ip: str, http_port: int) -> bool:
        try:
            conn = http.client.HTTPConnection(host_ip, http_port, timeout=3)
            conn.request('GET', '/status')
            resp = conn.getresponse()
            conn.close()
            return resp.status == 200
        except Exception:
            return False

    def _needs_reupload(self, filepath: Path, host_ip: str, http_port: int,
                        event_name: str, match_type: str,
                        match_number: str) -> bool:
        """Check if a previously uploaded file has changed by comparing SHA-256."""
        try:
            local_sha = hashlib.sha256(filepath.read_bytes()).hexdigest()

            conn = http.client.HTTPConnection(host_ip, http_port, timeout=5)
            headers = {
                'X-Filename': filepath.name,
                'X-Event-Name': event_name or '',
                'X-Match-Type': match_type or '',
                'X-Match-Number': match_number or '',
            }
            conn.request('GET', '/check', headers=headers)
            resp = conn.getresponse()
            body = json.loads(resp.read().decode('utf-8'))
            conn.close()

            if resp.status != 200:
                return False

            if not body.get('exists'):
                return True

            remote_sha = body.get('sha256', '')
            if local_sha != remote_sha:
                logger.info(f"SHA-256 mismatch for {filepath.name}, will re-upload")
                return True

            return False
        except Exception:
            logger.exception(f"Failed to check {filepath.name}")
            return False

    def _upload_file(self, filepath: Path, host_ip: str, http_port: int,
                     event_name: str, match_type: str, match_number: str,
                     overwrite: bool = False) -> bool:
        try:
            raw_data = filepath.read_bytes()
            if len(raw_data) == 0:
                logger.info(f"Skipping {filepath.name}: file is empty (0 bytes)")
                self._control.send_message({
                    'type': 'FILE_SKIPPED',
                    'filename': filepath.name,
                    'reason': 'empty (0 bytes)',
                })
                return True  # Treat as "handled" so it gets added to manifest
            compressed_data = zlib.compress(raw_data)

            conn = http.client.HTTPConnection(host_ip, http_port, timeout=30)
            headers = {
                'Content-Type': 'application/octet-stream',
                'Content-Encoding': 'deflate',
                'X-Filename': filepath.name,
                'X-Event-Name': event_name or '',
                'X-Match-Type': match_type or '',
                'X-Match-Number': match_number or '',
                'X-Uncompressed-Size': str(len(raw_data)),
                'Content-Length': str(len(compressed_data)),
            }
            if overwrite:
                headers['X-Overwrite'] = 'true'

            start_time = time.monotonic()
            conn.request('POST', '/upload', body=compressed_data, headers=headers)
            resp = conn.getresponse()
            conn.close()
            elapsed = time.monotonic() - start_time
            raw_mb = len(raw_data) / (1024 * 1024)
            compressed_mb = len(compressed_data) / (1024 * 1024)
            rate_mbps = compressed_mb / elapsed if elapsed > 0 else 0
            savings = (1 - len(compressed_data) / len(raw_data)) * 100 if raw_data else 0

            if resp.status == 200:
                action = "Re-uploaded" if overwrite else "Uploaded"
                logger.info(f"{action} {filepath.name} "
                            f"({raw_mb:.1f} MB → {compressed_mb:.1f} MB compressed, "
                            f"{savings:.0f}% savings, {elapsed:.2f}s, {rate_mbps:.1f} MB/s)")
                return True
            elif resp.status == 409:
                logger.info(f"Already exists on receiver: {filepath.name}")
                return True
            else:
                logger.warning(
                    f"Upload failed for {filepath.name}: HTTP {resp.status}"
                )
                return False
        except Exception:
            logger.exception(f"Upload failed for {filepath.name}")
            return False
