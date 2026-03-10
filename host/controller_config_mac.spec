# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Controller Config GUI (macOS).

Build with:
    cd host
    pyinstaller controller_config_mac.spec --distpath ../dist --workpath ../build/gui --clean -y
"""

a = Analysis(
    ['controller_config/main.py'],
    pathex=['..'],
    datas=[
        ('../images/Xbox_Controller.svg.png', 'images'),
        ('../images/raptacongear.png', 'images'),
        ('../images/rumble.svg', 'images'),
        ('../images/Raptacon3200-BG-BW.png', 'images'),
        ('../images/XboxControlIcons/Buttons Full Solid', 'images/XboxControlIcons/Buttons Full Solid'),
        ('../utils/__init__.py', 'utils'),
        ('../utils/controller', 'utils/controller'),
        ('../utils/math', 'utils/math'),
    ],
    hiddenimports=[
        'utils',
        'utils.controller',
        'utils.controller.model',
        'utils.controller.config_io',
        'utils.math',
        'utils.math.curves',
    ],
    excludes=['cairosvg', 'cairo', 'XInput'],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='raptacon-controls-editor',
    console=False,
    onefile=True,
)
