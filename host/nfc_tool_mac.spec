# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the NFC Battery Tag Tool (macOS).

Build with:
    cd host
    pyinstaller nfc_tool_mac.spec --distpath ../dist --workpath ../build/gui --clean -y
"""

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
    excludes=['cairosvg', 'cairo', 'XInput'],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='raptacon-nfc-tool',
    console=False,
    onefile=True,
)
