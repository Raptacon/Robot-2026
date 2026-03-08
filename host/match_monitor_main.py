"""Standalone entry point for Match Monitor (used by PyInstaller).

Running directly:  python match_monitor_main.py [args]
Built exe:         pyinstaller match_monitor_win.spec
"""
from match_monitor.__main__ import main

main()
