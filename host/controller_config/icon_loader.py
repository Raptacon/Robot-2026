"""Centralized Xbox controller icon loading, theming, and caching.

Loads pre-split 256px transparent PNGs from the XboxControlIcons pack.
Selects Black or White variant based on system color scheme, adds colored
backgrounds for A/B/X/Y face buttons, and composites diagonal D-pad icons.

Xbox Series Button Icons and Controls by Zacksly
Licensed under CC BY 3.0 - https://zacksly.itch.io
"""

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageTk

# Input name -> icon filename(s) in Buttons Full Solid/{Black|White}/256w/
# Tuple values indicate compositing (layer both images together).
INPUT_ICON_MAP: dict[str, str | tuple[str, str]] = {
    # Face buttons (get colored backgrounds)
    "a_button": "A.png",
    "b_button": "B.png",
    "x_button": "X.png",
    "y_button": "Y.png",
    # Bumpers & triggers
    "left_bumper": "Left Bumper.png",
    "right_bumper": "Right Bumper.png",
    "left_trigger": "Left Trigger.png",
    "right_trigger": "Right Trigger.png",
    # Stick buttons
    "left_stick_button": "Left Stick Click.png",
    "right_stick_button": "Right Stick Click.png",
    # Stick axes
    "left_stick_x": "Left Stick Left-Right.png",
    "left_stick_y": "Left Stick Up-Down.png",
    "right_stick_x": "Right Stick Left-Right.png",
    "right_stick_y": "Right Stick Up-Down.png",
    # D-pad cardinal directions
    "pov_up": "D-Pad Up.png",
    "pov_down": "D-Pad Down.png",
    "pov_left": "D-Pad Left.png",
    "pov_right": "D-Pad Right.png",
    # D-pad diagonals (composite two cardinal icons)
    "pov_up_right": ("D-Pad Up.png", "D-Pad Right.png"),
    "pov_down_right": ("D-Pad Down.png", "D-Pad Right.png"),
    "pov_down_left": ("D-Pad Down.png", "D-Pad Left.png"),
    "pov_up_left": ("D-Pad Up.png", "D-Pad Left.png"),
    # Special buttons
    "back_button": "View.png",
    "start_button": "Menu.png",
    # rumble_* uses existing rumble.svg — not in this icon pack
}

# Xbox brand colors for face button backgrounds
FACE_BUTTON_COLORS = {
    "a_button": "#107C10",
    "b_button": "#B7191C",
    "x_button": "#0078D7",
    "y_button": "#FFB900",
}


class InputIconLoader:
    """Loads and caches Xbox controller input icons.

    Selects Black or White icon variant based on the system color scheme.
    Face buttons (A/B/X/Y) get colored circle backgrounds.
    Diagonal D-pad icons are composited from two cardinal directions.
    """

    def __init__(self, icons_base_dir: Path, root=None):
        """Initialize the icon loader.

        Args:
            icons_base_dir: Path to ``Buttons Full Solid/`` directory
                containing ``Black/256w/`` and ``White/256w/`` subdirs.
            root: Optional tkinter root widget for theme detection.
                If ``None``, defaults to Black icons.
        """
        self._base_dir = icons_base_dir
        self._root = root
        self._use_white = False
        self._pil_cache: dict[tuple[str, int], Image.Image] = {}
        self._tk_cache: dict[tuple[str, int], ImageTk.PhotoImage] = {}
        if root is not None:
            self._detect_theme()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tk_icon(
        self, input_name: str, size: int = 16
    ) -> Optional[ImageTk.PhotoImage]:
        """Return a cached tkinter PhotoImage for the given input and size."""
        key = (input_name, size)
        if key in self._tk_cache:
            return self._tk_cache[key]
        pil_img = self.get_pil_icon(input_name, size)
        if pil_img is None:
            return None
        tk_img = ImageTk.PhotoImage(pil_img)
        self._tk_cache[key] = tk_img
        return tk_img

    def get_pil_icon(
        self, input_name: str, size: int = 16
    ) -> Optional[Image.Image]:
        """Return a cached PIL RGBA image for the given input and size."""
        key = (input_name, size)
        if key in self._pil_cache:
            return self._pil_cache[key]
        img = self._build_icon(input_name, size)
        if img is not None:
            self._pil_cache[key] = img
        return img

    def refresh_theme(self):
        """Re-detect system theme and clear all caches."""
        if self._root is not None:
            self._detect_theme()
        self._pil_cache.clear()
        self._tk_cache.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect_theme(self):
        """Detect light/dark mode from the default background color."""
        try:
            bg = self._root.cget("background")
            r, g, b = self._root.winfo_rgb(bg)
            # winfo_rgb returns 16-bit values (0-65535)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 65535
            self._use_white = luminance < 0.5
        except Exception:
            self._use_white = False

    def _icon_dir(self, variant: str = "") -> Path:
        """Return the 256w directory for the given variant."""
        if not variant:
            variant = "White" if self._use_white else "Black"
        return self._base_dir / variant / "256w"

    def _load_raw(self, filename: str, variant: str = "") -> Optional[Image.Image]:
        """Load a single icon PNG as RGBA."""
        path = self._icon_dir(variant) / filename
        if not path.exists():
            return None
        return Image.open(path).convert("RGBA")

    def _build_icon(self, input_name: str, size: int) -> Optional[Image.Image]:
        """Build the final icon image for an input at the requested size."""
        mapping = INPUT_ICON_MAP.get(input_name)
        if mapping is None:
            return None

        # Face buttons: colored background + white icon on top
        if input_name in FACE_BUTTON_COLORS:
            img = self._build_face_button(input_name, mapping)
        elif isinstance(mapping, tuple):
            # Diagonal D-pad: composite two cardinal directions
            img = self._build_composite(mapping)
        else:
            img = self._load_raw(mapping)

        if img is None:
            return None

        # Resize with high-quality resampling
        img = img.resize((size, size), Image.LANCZOS)
        return img

    def _build_face_button(
        self, input_name: str, filename: str
    ) -> Optional[Image.Image]:
        """Build a face button icon with colored circle background."""
        # Always use White variant for face buttons (white letter on color)
        icon = self._load_raw(filename, variant="White")
        if icon is None:
            return None

        w, h = icon.size
        color_hex = FACE_BUTTON_COLORS[input_name]
        r = int(color_hex[1:3], 16)
        g = int(color_hex[3:5], 16)
        b = int(color_hex[5:7], 16)

        # Create colored circle background matching icon size
        bg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(bg)
        # The icon is a circle centered in the image with some padding
        # Draw a filled circle slightly larger than the icon's circle
        padding = int(w * 0.12)
        draw.ellipse(
            [padding, padding, w - padding, h - padding],
            fill=(r, g, b, 255),
        )

        # Composite white icon on top of colored circle
        result = Image.alpha_composite(bg, icon)
        return result

    def _build_composite(
        self, filenames: tuple[str, str]
    ) -> Optional[Image.Image]:
        """Composite two icon images together (for diagonal D-pad)."""
        img1 = self._load_raw(filenames[0])
        img2 = self._load_raw(filenames[1])
        if img1 is None or img2 is None:
            return img1 or img2
        return Image.alpha_composite(img1, img2)
