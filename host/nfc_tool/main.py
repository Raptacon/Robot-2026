"""Entry point for the NFC Battery Tag Tool GUI.

Usage:
    python -m host.nfc_tool
"""

import sys
from pathlib import Path

_HAS_TKINTER = True
try:
    import tkinter as _tkinter  # noqa: F401
except ImportError:
    _HAS_TKINTER = False


def _get_project_root():
    """Return the project root, handling PyInstaller frozen bundles."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


# Ensure project root is importable (for utils.nfc)
_project_root = _get_project_root()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def main():
    if not _HAS_TKINTER:
        print(
            "Error: tkinter is not installed.\n"
            "On macOS with Homebrew Python, run:\n"
            "    brew install python-tk\n"
            "Then retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    from host.nfc_tool.app import NfcToolApp

    app = NfcToolApp(project_root=_project_root)
    app.mainloop()


if __name__ == "__main__":
    main()
