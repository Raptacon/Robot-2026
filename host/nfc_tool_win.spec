# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the NFC Battery Tag Tool (Windows).

Build with:
    cd host
    pyinstaller nfc_tool_win.spec --distpath ../dist --workpath ../build/gui --clean -y
"""

import os

_ico_path = os.path.join('..', 'images', 'Raptacon3200-BG-BW.ico')
_has_ico = os.path.exists(_ico_path)

a = Analysis(
    ['nfc_tool/main.py'],
    pathex=['..'],
    datas=[
        ('../images/raptacongear.png', 'images'),
        ('../images/Raptacon3200-BG-BW.png', 'images'),
        ('../utils/__init__.py', 'utils'),
        ('../utils/nfc', 'utils/nfc'),
    ],
    hiddenimports=[
        'utils',
        'utils.nfc',
        'utils.nfc.nfc_reader',
        'utils.nfc.nfc_serial_transport',
        'utils.nfc.nfc_writer',
    ],
    excludes=['cairosvg', 'cairo'],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='raptacon-nfc-tool',
    console=False,
    icon=_ico_path if _has_ico else None,
    onefile=True,
)
