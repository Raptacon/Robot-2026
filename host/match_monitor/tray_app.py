"""
System tray application for Match Monitor (Windows).

Launch via:  python -m host.match_monitor --tray

__main__.py automatically re-launches under pythonw.exe so the originating
cmd/PowerShell window closes immediately and no console is left open.

The "Open Console" tray menu item allocates a fresh Windows console window
(via AllocConsole) on demand.  "Close Console" frees it.  The console runs
the interactive monitor> prompt and can be opened/closed independently.
"""

import ctypes
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger("match_monitor")

if hasattr(sys, '_MEIPASS'):
    # Running as a PyInstaller frozen exe — data files land in _MEIPASS
    _LOGO_PATH = Path(sys._MEIPASS) / 'images' / 'raptacongear.png'
else:
    _LOGO_PATH = Path(__file__).parent.parent.parent / 'images' / 'raptacongear.png'

_STATUS_COLORS = {
    'idle':      '#808080',  # gray  — polling
    'connected': '#57F287',  # green — connected
    'uploading': '#FEE75C',  # yellow — uploading
    'error':     '#ED4245',  # red   — error
}

_ICON_CACHE: dict = {}


def _make_icon(status: str, size: int = 64):
    """Raptacon gear logo with a small colored status badge (bottom-right)."""
    from PIL import Image, ImageDraw

    color = _STATUS_COLORS.get(status, _STATUS_COLORS['idle'])

    try:
        logo = Image.open(_LOGO_PATH).convert('RGBA').resize((size, size), Image.LANCZOS)
    except Exception:  # noqa: BLE001 — fall back to blank icon if logo missing/corrupt
        logo = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(logo).ellipse([4, 4, size - 4, size - 4], fill='#303030')

    draw = ImageDraw.Draw(logo)
    r = size // 5
    x0, y0 = size - r * 2 - 2, size - r * 2 - 2
    draw.ellipse([x0, y0, size - 2, size - 2], fill=color, outline='white', width=1)

    return logo


def _icon_for(status: str):
    if status not in _ICON_CACHE:
        _ICON_CACHE[status] = _make_icon(status)
    return _ICON_CACHE[status]


class MatchMonitorTray:
    """Wraps a ServerContext in a pystray system-tray icon."""

    def __init__(self, ctx) -> None:
        import pystray
        self._pystray = pystray
        self._ctx = ctx
        self._stop_requested = False

        # Console state — starts closed; opened on demand via AllocConsole()
        self._console_open = False
        self._console_hwnd = 0
        self._console_visible = False
        self._console_thread: threading.Thread | None = None

        self._icon = pystray.Icon(
            'MatchMonitor',
            _icon_for('idle'),
            'Match Monitor\nPolling for robot...',
            menu=pystray.Menu(self._menu_items),
        )

    # ------------------------------------------------------------------
    # Dynamic menu (rebuilt on each right-click)
    # ------------------------------------------------------------------

    def _menu_items(self):
        pystray = self._pystray
        info = self._ctx.connector.status_info
        state = info['state']
        connected = self._ctx.connector.is_connected

        uptime_str = ''
        if info['connected_since'] is not None:
            uptime = time.monotonic() - info['connected_since']
            mins, secs = divmod(int(uptime), 60)
            hrs, mins = divmod(mins, 60)
            uptime_str = f'  ({hrs}h {mins:02d}m {secs:02d}s)'

        if not self._console_open:
            console_item = pystray.MenuItem('Open Console', self._open_console)
        elif self._console_visible:
            console_item = pystray.MenuItem('Hide Console', self._hide_console)
        else:
            console_item = pystray.MenuItem('Show Console', self._show_console)

        return (
            pystray.MenuItem(f'● {state}{uptime_str}', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Robot', pystray.Menu(
                pystray.MenuItem('Force Upload',   self._force_upload,   enabled=connected),
                pystray.MenuItem('Stop Upload',    self._stop_upload,    enabled=connected),
                pystray.MenuItem('Clear Manifest', self._clear_manifest, enabled=connected),
                pystray.MenuItem('List Logs',      self._list_logs,      enabled=connected),
            )),
            pystray.MenuItem('Open Log Folder', self._open_log_folder),
            pystray.MenuItem('Set Code Directory...', self._set_code_dir),
            pystray.Menu.SEPARATOR,
            console_item,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self._quit),
        )

    # ------------------------------------------------------------------
    # Robot actions
    # ------------------------------------------------------------------

    def _force_upload(self):
        self._ctx.connector.send_to_robot({'type': 'FORCE_UPLOAD'})

    def _stop_upload(self):
        self._ctx.connector.send_to_robot({'type': 'STOP_UPLOAD'})

    def _clear_manifest(self):
        self._ctx.connector.send_to_robot({'type': 'CLEAR_MANIFEST'})

    def _list_logs(self):
        self._ctx.connector.send_to_robot({'type': 'LIST_LOGS'})

    def _open_log_folder(self):
        subprocess.Popen(['explorer', str(self._ctx.out_path)])

    def _set_code_dir(self):
        """Open a folder picker dialog to set the robot code directory.

        Runs the tkinter dialog in a subprocess because pystray callbacks
        execute on a background thread, and tkinter requires the main thread.
        """
        import subprocess
        import sys
        from pathlib import Path
        from .receiver import _save_config_key

        initial = str(self._ctx.code_dir_holder[0]) if self._ctx.code_dir_holder[0] else ''
        script = (
            "import tkinter as tk; from tkinter.filedialog import askdirectory; "
            "r=tk.Tk(); r.withdraw(); r.attributes('-topmost',True); "
            f"print(askdirectory(title='Select Robot Code Directory', initialdir={initial!r}) or ''); "
            "r.destroy()"
        )
        result = subprocess.run([sys.executable, '-c', script],
                                capture_output=True, text=True)
        chosen = result.stdout.strip()

        if not chosen:
            return

        new_path = Path(chosen).resolve()
        self._ctx.code_dir_holder[0] = new_path

        notifier = self._ctx.discord_holder[0]
        if notifier:
            notifier._repo_root = new_path

        _save_config_key(self._ctx.config_path, 'robot_code_dir', str(new_path))
        is_git = (new_path / '.git').exists()
        suffix = '' if is_git else ' (no .git)'
        logger.info(f"Code directory set to: {new_path}{suffix}")

    # ------------------------------------------------------------------
    # Console management
    # ------------------------------------------------------------------

    def _open_console(self):
        """Allocate a new Windows console window and start the monitor> prompt."""
        if self._console_open:
            self._show_console()
            return

        ctypes.windll.kernel32.AllocConsole()
        ctypes.windll.kernel32.SetConsoleTitleW("Match Monitor Console")

        # Redirect Python I/O to the new console
        try:
            sys.stdout = open('CONOUT$', 'w', buffering=1, encoding='utf-8',
                              errors='replace')
            sys.stderr = open('CONOUT$', 'w', buffering=1, encoding='utf-8',
                              errors='replace')
            sys.stdin = open('CONIN$', 'r', encoding='utf-8', errors='replace')
        except OSError as e:
            logger.warning(f"Could not redirect streams to console: {e}")
            return

        # Update the logging console handler to write to the new console
        self._ctx.console_handler.stream = sys.stdout
        self._ctx.console_handler.setLevel(logging.INFO)

        self._console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        self._console_open = True
        self._console_visible = True

        # Disable the console close (X) button.
        # CTRL_CLOSE_EVENT cannot be safely handled without Windows eventually
        # terminating the process — disabling the button avoids the problem
        # entirely.  Users close the console with 'exit' instead.
        _SC_CLOSE = 0xF060
        _MF_BYCOMMAND = 0
        _hmenu = ctypes.windll.user32.GetSystemMenu(self._console_hwnd, False)
        ctypes.windll.user32.DeleteMenu(_hmenu, _SC_CLOSE, _MF_BYCOMMAND)

        # Start the interactive monitor> prompt in the console
        from .receiver import _console_loop
        self._console_thread = threading.Thread(
            target=_console_loop,
            args=(self._ctx.connector, self._ctx.console_handler,
                  self._ctx.file_handler, self._ctx.log_dir,
                  self._ctx.registry, self._ctx.discord_holder,
                  self._ctx.config_path, self._ctx.code_dir_holder),
            kwargs={'analyzer': self._ctx.analyzer,
                    'out_path': self._ctx.out_path,
                    'match_client': self._ctx.match_client,
                    'quit_callback': self._quit,
                    'close_callback': self._on_console_closed},
            daemon=True,
        )
        self._console_thread.start()

        print("Match Monitor Console — type 'help' for commands.")

    def _on_console_closed(self):
        """Free the Windows console and reset state so it can be re-opened.

        Called after the console loop exits (exit command or stop-server).
        Must be idempotent.
        """
        if not self._console_open:
            return

        self._console_open = False
        self._console_visible = False
        self._console_hwnd = 0
        self._console_thread = None

        # Redirect logging handler away from the (about-to-be-freed) console
        import os
        _devnull = open(os.devnull, 'w')
        self._ctx.console_handler.stream = _devnull

        # Close stdin first — this unblocks any pending input() in the console
        # thread so it exits cleanly via EOFError/OSError.
        try:
            if sys.stdin is not None:
                sys.stdin.close()
            sys.stdin = None
        except Exception:
            logger.debug("Error closing stdin during console teardown", exc_info=True)

        # Detach from the console — window closes (we are the only process).
        ctypes.windll.kernel32.FreeConsole()

        # Close stdout/stderr after detaching (handles are now invalid)
        for attr in ('stdout', 'stderr'):
            try:
                s = getattr(sys, attr, None)
                if s is not None:
                    s.close()
            except Exception:
                logger.debug("Error closing %s during console teardown", attr, exc_info=True)
            setattr(sys, attr, None)

        # Force the tray menu to rebuild so "Open Console" replaces "Hide Console"
        try:
            self._icon.update_menu()
        except Exception:
            logger.debug("Error updating tray menu after console close", exc_info=True)

    def _hide_console(self):
        if self._console_hwnd:
            ctypes.windll.user32.ShowWindow(self._console_hwnd, 0)  # SW_HIDE
        self._console_visible = False

    def _show_console(self):
        if self._console_hwnd:
            ctypes.windll.user32.ShowWindow(self._console_hwnd, 5)  # SW_SHOW
            ctypes.windll.user32.SetForegroundWindow(self._console_hwnd)
        self._console_visible = True

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def _quit(self):
        """Stop the tray icon — cleanup runs in run() after icon.run() returns."""
        self._stop_requested = True
        self._icon.stop()

    # ------------------------------------------------------------------
    # Background update loop
    # ------------------------------------------------------------------

    def _update_loop(self) -> None:
        while not self._stop_requested:
            time.sleep(2)
            try:
                info = self._ctx.connector.status_info
                state_str = info['state'].lower()

                if 'uploading' in state_str:
                    icon_state = 'uploading'
                    tooltip = 'Match Monitor\nUploading logs...'
                elif 'connected' in state_str:
                    icon_state = 'connected'
                    robot = info.get('robot_address') or ''
                    uptime = ''
                    if info['connected_since'] is not None:
                        secs = int(time.monotonic() - info['connected_since'])
                        m, s = divmod(secs, 60)
                        h, m = divmod(m, 60)
                        uptime = f'  {h}h {m:02d}m {s:02d}s'
                    tooltip = f'Match Monitor\nConnected: {robot}{uptime}'
                else:
                    icon_state = 'idle'
                    tooltip = 'Match Monitor\nPolling for robot...'

                self._icon.icon = _icon_for(icon_state)
                self._icon.title = tooltip
            except Exception:
                logger.debug("Error updating tray icon", exc_info=True)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the HTTP server in background, run the tray on the main thread."""
        threading.Thread(
            target=self._ctx.server.serve_forever,
            daemon=True,
        ).start()

        threading.Thread(target=self._update_loop, daemon=True).start()

        logger.info("Match Monitor tray started")
        try:
            self._icon.run()  # blocks until _quit() calls icon.stop()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down")

        # --- Cleanup after tray icon stops ---
        self._stop_requested = True
        self._ctx.connector.stop()
        logger.info("Match Monitor tray shutting down")
        threading.Thread(target=self._ctx.server.shutdown, daemon=True).start()
        sys.exit(0)


def run_server_tray(bind: str, port: int, output_dir: str = None,
                    debug: bool = False) -> None:
    """Set up the server and run it as a system tray application."""
    from .receiver import setup_server

    ctx = setup_server(bind, port, output_dir, debug)
    logger.info(f"Match Monitor tray on {bind}:{port}, saving to {ctx.out_path}")

    MatchMonitorTray(ctx).run()
