"""NFC Battery Tag Tool — main application window.

Coordinates the serial panel, tabs, and background NFC worker thread.
All NFC I/O runs on a background thread; results are dispatched to tabs
via tkinter after() polling.
"""

import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from utils.nfc.nfc_serial_transport import NfcSerialTransport
from utils.nfc.nfc_reader import NfcReader
from utils.nfc.nfc_writer import build_battery_ndef

from host.nfc_tool.serial_panel import SerialPanel
from host.nfc_tool.scan_tab import ScanTab
from host.nfc_tool.read_tab import ReadTab
from host.nfc_tool.write_tab import WriteTab

logger = logging.getLogger(__name__)

# Commands sent to worker thread
CMD_CONNECT = 'connect'
CMD_DISCONNECT = 'disconnect'
CMD_POLL = 'poll'
CMD_WRITE = 'write'
CMD_STOP = 'stop'


class NfcWorker(threading.Thread):
    """Background thread for all NFC serial I/O."""

    def __init__(self):
        super().__init__(daemon=True)
        self.cmd_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self._transport = None
        self._reader = None

    def run(self):
        while True:
            try:
                cmd = self.cmd_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if cmd[0] == CMD_STOP:
                self._cleanup()
                break
            elif cmd[0] == CMD_CONNECT:
                self._do_connect(cmd[1])
            elif cmd[0] == CMD_DISCONNECT:
                self._do_disconnect()
            elif cmd[0] == CMD_POLL:
                self._do_poll(cmd[1])
            elif cmd[0] == CMD_WRITE:
                self._do_write(cmd[1])

    def _do_connect(self, port):
        try:
            self._transport = NfcSerialTransport(port, timeout=0.2)
            if not self._transport.open():
                self.result_queue.put(
                    ('connected', False, "Failed to open serial port"))
                return
            self._reader = NfcReader(self._transport)
            if not self._reader.begin():
                self._transport.close()
                self.result_queue.put(
                    ('connected', False, "PN532 init failed"))
                return
            self.result_queue.put(('connected', True, ''))
        except Exception as e:
            self.result_queue.put(('connected', False, str(e)))

    def _do_disconnect(self):
        self._cleanup()
        self.result_queue.put(('disconnected',))

    def _do_poll(self, source):
        if self._reader is None or not self._reader.is_ready:
            self.result_queue.put(('tag_data', source, None))
            return
        try:
            tag_data = self._reader.read_full_tag(
                user_data_start=4, user_data_pages=128)
            self.result_queue.put(('tag_data', source, tag_data))
        except Exception as e:
            logger.debug("Poll error: %s", e)
            self.result_queue.put(('tag_data', source, None))

    def _do_write(self, params):
        if self._reader is None or not self._reader.is_ready:
            self.result_queue.put(
                ('write_result', False, "Reader not connected"))
            return
        try:
            # Build NDEF data
            ndef_bytes = build_battery_ndef(
                sn=params['sn'],
                year=params['year'],
                note=params.get('note', ''),
                uri=params.get('uri', 'http://www.raptacon.org'),
            )

            # Detect tag (fresh target listing for write)
            result = self._reader.read_passive_target()
            if result is None:
                self.result_queue.put(
                    ('write_result', False, "No tag detected"))
                return

            tg, uid = result

            # Pad NDEF with zeros to clear any old data beyond it
            write_data = bytearray(ndef_bytes)
            write_data.extend(b'\x00' * 32)

            # Write starting at page 4
            if not self._reader.write_ntag_pages(
                    tg, 4, bytes(write_data)):
                self.result_queue.put(
                    ('write_result', False, "Page write failed"))
                return

            self.result_queue.put(('write_result', True, ''))

        except ValueError as e:
            self.result_queue.put(('write_result', False, str(e)))
        except Exception as e:
            logger.exception("Write error")
            self.result_queue.put(('write_result', False, str(e)))

    def _cleanup(self):
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None
            self._reader = None


class NfcToolApp(tk.Tk):
    """Main NFC Battery Tag Tool window."""

    def __init__(self, project_root=None):
        super().__init__()
        self.title("NFC Battery Tag Tool \u2014 Team 3200")
        self.geometry("650x550")
        self.minsize(500, 400)

        self._project_root = Path(project_root) if project_root else None
        self._load_icon()

        # Worker thread
        self._worker = NfcWorker()
        self._worker.start()

        self._build_ui()

        # Poll worker results
        self._check_results()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_icon(self):
        """Set the window icon from the Raptacon logo."""
        if self._project_root is None:
            return
        icon_path = self._project_root / "images" / "Raptacon3200-BG-BW.png"
        if icon_path.exists():
            try:
                self._icon_image = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, self._icon_image)
            except Exception:
                pass

    def _load_gear_logo(self, parent):
        """Load the gear logo and return a Label widget, or None."""
        if self._project_root is None:
            return None
        logo_path = self._project_root / "images" / "raptacongear.png"
        if not logo_path.exists():
            return None
        try:
            img = tk.PhotoImage(file=str(logo_path))
            # Subsample to ~64px (original is large)
            w = img.width()
            factor = max(1, w // 64)
            img = img.subsample(factor, factor)
            self._gear_image = img  # prevent GC
            label = ttk.Label(parent, image=img)
            return label
        except Exception:
            return None

    def _build_ui(self):
        # Header with serial panel and logo
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))

        # Serial panel (left side)
        self._serial_panel = SerialPanel(
            header,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
        )
        self._serial_panel.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Gear logo (right side)
        logo = self._load_gear_logo(header)
        if logo:
            logo.pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8)

        # Tabs
        self._notebook = ttk.Notebook(self)

        self._scan_tab = ScanTab(
            self._notebook, request_poll=self._request_poll)
        self._read_tab = ReadTab(
            self._notebook, request_poll=self._request_poll)
        self._write_tab = WriteTab(
            self._notebook,
            request_poll=self._request_poll,
            request_write=self._request_write,
        )

        self._notebook.add(self._scan_tab, text="Scan")
        self._notebook.add(self._read_tab, text="Read")
        self._notebook.add(self._write_tab, text="Write Battery Tag")

        self._notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._tabs = [self._scan_tab, self._read_tab, self._write_tab]
        self._active_tab_idx = 0

    def _on_tab_changed(self, event):
        # Notify old tab
        if 0 <= self._active_tab_idx < len(self._tabs):
            self._tabs[self._active_tab_idx].on_tab_deselected()

        # Notify new tab
        idx = self._notebook.index(self._notebook.select())
        self._active_tab_idx = idx
        if 0 <= idx < len(self._tabs):
            self._tabs[idx].on_tab_selected()

    def _on_connect(self, port):
        self._worker.cmd_queue.put((CMD_CONNECT, port))

    def _on_disconnect(self):
        # Stop any tab polling
        for tab in self._tabs:
            tab.on_tab_deselected()
        self._worker.cmd_queue.put((CMD_DISCONNECT,))

    def _request_poll(self, source):
        """Tabs call this to request a tag poll."""
        if not self._serial_panel.is_connected:
            return
        self._worker.cmd_queue.put((CMD_POLL, source))

    def _request_write(self, sn, year, note='', uri=''):
        """Write tab calls this to perform the actual write."""
        self._worker.cmd_queue.put((CMD_WRITE, {
            'sn': sn, 'year': year, 'note': note, 'uri': uri,
        }))

    def _check_results(self):
        """Poll worker result queue and dispatch to tabs."""
        try:
            while True:
                result = self._worker.result_queue.get_nowait()
                self._handle_result(result)
        except queue.Empty:
            pass
        self.after(100, self._check_results)

    def _handle_result(self, result):
        cmd = result[0]

        if cmd == 'connected':
            success, error_msg = result[1], result[2]
            self._serial_panel.set_connected(success, error_msg)
            if success:
                # Activate current tab's polling
                idx = self._active_tab_idx
                if 0 <= idx < len(self._tabs):
                    self._tabs[idx].on_tab_selected()

        elif cmd == 'disconnected':
            self._serial_panel.set_disconnected()

        elif cmd == 'tag_data':
            source, tag_data = result[1], result[2]
            if source == 'scan':
                self._scan_tab.update_tag_data(tag_data)
            elif source == 'read':
                self._read_tab.update_tag_data(tag_data)
            elif source == 'write_search':
                self._write_tab.on_search_result(tag_data)
            elif source == 'write_verify':
                self._write_tab.on_verify_result(tag_data)

        elif cmd == 'write_result':
            success, error_msg = result[1], result[2]
            self._write_tab.on_write_result(success, error_msg)

    def _on_close(self):
        # Stop all tab polling
        for tab in self._tabs:
            tab.on_tab_deselected()
        # Stop worker
        self._worker.cmd_queue.put((CMD_STOP,))
        self._worker.join(timeout=2.0)
        self.destroy()
