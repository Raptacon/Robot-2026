"""Robot-side wiring for the match-monitor host connection.

Owns the TCP `ControlListener` and the `LogUploader`, wires their
callbacks, and exposes the small surface that `robot.py` needs
(`start_upload` / `stop_upload`). If either component fails to
construct, the connection degrades to a no-op so robot init still
succeeds.
"""

import logging
from typing import Optional

import wpilib

from utils.match_monitor.control_listener import ControlListener
from utils.match_monitor.log_uploader import LogUploader

logger = logging.getLogger(__name__)


class MatchMonitorConnection:
    """Listener + uploader pair, wired together and started."""

    def __init__(self) -> None:
        self.listener: Optional[ControlListener] = None
        self.uploader: Optional[LogUploader] = None

        try:
            self.listener = ControlListener()
            self.listener.start()
        except Exception:
            wpilib.reportError("Unable to create ControlListener", printTrace=True)
            return

        try:
            self.uploader = LogUploader(self.listener)
        except Exception:
            wpilib.reportError("Unable to create LogUploader", printTrace=True)
            return

        self.listener.on_force_upload = self.uploader.start_upload
        self.listener.on_stop_upload = self.uploader.stop_upload
        self.listener.on_clear_manifest_done = self._on_clear_manifest

    def start_upload(self) -> None:
        if self.uploader is not None:
            self.uploader.start_upload()

    def stop_upload(self) -> None:
        if self.uploader is not None:
            self.uploader.stop_upload()

    def _on_clear_manifest(self) -> None:
        # Let current file finish uploading, then stop, clear, restart.
        self.uploader.stop_and_wait()
        count = self.listener._clear_manifests()
        self.listener.send_message({'type': 'MANIFEST_CLEARED', 'count': count})
        self.uploader.start_upload()
