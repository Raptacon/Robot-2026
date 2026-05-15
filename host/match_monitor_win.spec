# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Match Monitor (Windows).

Build with:
    cd host
    pyinstaller match_monitor_win.spec --distpath ../dist --workpath ../build/match_monitor --clean -y
"""

import os
import sys
import glob as _glob

_ico_path = os.path.join('..', 'images', 'Raptacon3200-BG-BW.ico')
_has_ico = os.path.exists(_ico_path)

# Locate wpiutil.dll — installed by robotpy-wpiutil under native/wpiutil/lib/
_wpiutil_dll = _glob.glob(
    os.path.join(sys.exec_prefix, 'Lib', 'site-packages', 'native', 'wpiutil', 'lib', 'wpiutil.dll')
)
_extra_binaries = [(_wpiutil_dll[0], '.') ] if _wpiutil_dll else []

a = Analysis(
    ['match_monitor_main.py'],
    pathex=['..', '.'],   # repo root (utils/) and host/ (match_monitor/)
    binaries=_extra_binaries,
    datas=[
        ('../images/raptacongear.png', 'images'),
    ],
    hiddenimports=[
        'match_monitor',
        'match_monitor.__main__',
        'match_monitor.receiver',
        'match_monitor.tray_app',
        'match_monitor.connector',
        'match_monitor.analyzer',
        'match_monitor.callbacks',
        'match_monitor.ds_log_reader',
        'match_monitor.match_data_client',
        'match_monitor.discord_notifier',
        'match_monitor.quotes',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'tkinter',
        'tkinter.filedialog',
    ],
    excludes=['robotpy', 'wpilib', 'commands2'],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='raptacon-match-monitor',
    console=False,
    icon=_ico_path if _has_ico else None,
    onefile=True,
)
