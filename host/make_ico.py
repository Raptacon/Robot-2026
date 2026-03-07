"""Convert team PNG logo to .ico for PyInstaller EXE icon.

Usage:
    python host/make_ico.py

Generates images/Raptacon3200-BG-BW.ico from the existing PNG.
"""

from pathlib import Path
from PIL import Image

_root = Path(__file__).resolve().parent.parent
_src = _root / "images" / "Raptacon3200-BG-BW.png"
_dst = _root / "images" / "Raptacon3200-BG-BW.ico"

img = Image.open(_src)
img.save(
    _dst,
    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print(f"Created: {_dst}")
