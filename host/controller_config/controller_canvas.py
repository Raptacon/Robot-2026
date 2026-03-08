"""Canvas widget that renders the Xbox controller image with binding overlays.

Draws leader lines from each controller input to binding boxes showing
assigned actions. Bold outlines are drawn around each button on the
controller image and are clickable to assign bindings.  Binding boxes
are draggable — custom positions persist across sessions.
"""

import io
import math
import sys
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageDraw, ImageTk

from .layout_coords import (
    XBOX_INPUTS, XBOX_SHAPES, InputCoord, ButtonShape, _IMG_W, _IMG_H,
)

# Try cairosvg for crisp SVG rendering, fall back to pre-rendered PNG
try:
    import cairosvg
    HAS_CAIROSVG = True
except (ImportError, OSError):
    HAS_CAIROSVG = False

# Reference visual constants (at image scale 1.0, i.e. rendered_h == _IMG_H)
# Actual sizes are computed per-redraw by _compute_scaled_sizes().
_REF_BOX_WIDTH = 220
_REF_BOX_HEIGHT = 40
_REF_BOX_PAD = 6
_REF_LABEL_FONT = 12
_REF_ACTION_FONT = 14
_REF_PLUS_FONT = 28
_REF_LABEL_Y = 22       # y offset for action text below label
_REF_ACTION_STEP = 28   # y step per action line

# Defaults used before first redraw
BOX_WIDTH = _REF_BOX_WIDTH
BOX_HEIGHT = _REF_BOX_HEIGHT
BOX_PAD = _REF_BOX_PAD
LINE_COLOR = "#555555"
LINE_SELECTED_COLOR = "#cc0000"
BOX_OUTLINE = "#888888"
BOX_FILL = "#f0f0f0"
BOX_FILL_HOVER = "#ddeeff"
BOX_FILL_ASSIGNED = "#d4edda"
UNASSIGNED_TEXT = "(unassigned)"
UNASSIGNED_COLOR = "#999999"
ASSIGNED_COLOR = "#222222"
AXIS_INDICATOR_COLORS = {"X": "#cc4444", "Y": "#4444cc"}

# Shape overlay constants
SHAPE_OUTLINE_COLOR = "#4488cc"
SHAPE_OUTLINE_WIDTH = 2.5
SHAPE_HOVER_FILL = "#4488cc"
SHAPE_HOVER_STIPPLE = "gray25"

# Drag threshold in pixels — must move this far before drag starts
_DRAG_THRESHOLD = 5


def _image_search_bases() -> list[Path]:
    """Return candidate base directories for image lookup."""
    if getattr(sys, 'frozen', False):
        return [Path(sys._MEIPASS)]
    here = Path(__file__).resolve().parent
    return [here, here.parent, here.parent.parent]


def _find_image_path() -> Path:
    """Locate the Xbox controller image relative to the project root."""
    for base in _image_search_bases():
        svg_path = base / "images" / "Xbox_Controller.svg"
        if svg_path.exists():
            return svg_path
        png_path = base / "images" / "Xbox_Controller.svg.png"
        if png_path.exists():
            return png_path
    raise FileNotFoundError("Cannot find Xbox_Controller image in images/")


def _find_gear_icon() -> Path | None:
    """Locate the team gear logo image relative to the project root."""
    for base in _image_search_bases():
        png_path = base / "images" / "raptacongear.png"
        if png_path.exists():
            return png_path
    return None


def _find_rumble_icon() -> Path | None:
    """Locate the rumble icon image relative to the project root."""
    for base in _image_search_bases():
        svg_path = base / "images" / "rumble.svg"
        if svg_path.exists():
            return svg_path
        png_path = base / "images" / "rumble.png"
        if png_path.exists():
            return png_path
    return None


class ControllerCanvas(tk.Frame):
    """Displays the Xbox controller with interactive binding boxes and
    clickable button outlines."""

    def __init__(self, parent, on_binding_click=None, on_binding_clear=None,
                 on_mouse_coord=None, on_label_moved=None,
                 on_hover_input=None, on_hover_shape=None,
                 on_action_remove=None,
                 label_positions=None,
                 icon_loader=None):
        """
        Args:
            parent: tkinter parent widget
            on_binding_click: callback(input_name: str) when a binding is clicked
            on_binding_clear: callback(input_name: str) to clear an input's bindings
            on_mouse_coord: callback(img_x: int, img_y: int) with mouse
                position in source-image pixel space (1920x1292)
            on_label_moved: callback(input_name: str, img_x: int, img_y: int)
                when a binding box is dragged to a new position
            on_hover_input: callback(input_name: str | None) when hovering
                over a binding box (None when hover leaves)
            on_hover_shape: callback(input_names: list[str] | None) when
                hovering over a controller shape (None when hover leaves)
            on_action_remove: callback(input_name: str, action_name: str) to
                remove a single action from an input's bindings
            label_positions: dict mapping input_name -> [img_x, img_y] for
                custom label positions (loaded from settings)
        """
        super().__init__(parent)
        self._on_binding_click = on_binding_click
        self._on_binding_clear = on_binding_clear
        self._on_mouse_coord = on_mouse_coord
        self._on_label_moved = on_label_moved
        self._on_hover_input = on_hover_input
        self._on_hover_shape = on_hover_shape
        self._on_action_remove = on_action_remove
        self._icon_loader = icon_loader
        self._label_icon_refs: list[ImageTk.PhotoImage] = []
        self._bindings: dict[str, list[str]] = {}

        # Custom label positions: input_name -> (img_px_x, img_px_y)
        self._custom_label_pos: dict[str, tuple[int, int]] = {}
        if label_positions:
            for name, pos in label_positions.items():
                if isinstance(pos, (list, tuple)) and len(pos) == 2:
                    self._custom_label_pos[name] = (int(pos[0]), int(pos[1]))

        # DPI-aware font scaling: tkinter font sizes are in points (1/72 inch).
        # At 96 DPI (Windows), 9pt = 12 physical pixels.
        # At 72 DPI (macOS), 9pt = 9 physical pixels — 25% smaller.
        # Correct by scaling fonts up to match the Windows 96 DPI baseline.
        try:
            actual_dpi = self.winfo_fpixels('1i')
            self._dpi_scale = max(96.0 / actual_dpi, 1.0)
        except Exception:
            self._dpi_scale = 1.0

        # Initialize scaled sizes at reference scale (updated each redraw)
        self._compute_scaled_sizes(1.0)

        # Canvas item tracking
        self._box_items: dict[str, list[int]] = {}      # input_name -> item ids
        self._line_items: dict[str, int] = {}            # input_name -> line item id
        self._shape_items: dict[str, int] = {}           # shape.name -> canvas item id
        self._connector_group_items: dict[str, tuple[int, int | None]] = {}
        self._shape_map: dict[str, ButtonShape] = {}     # shape.name -> ButtonShape

        self._hover_input: str | None = None    # hovered binding box
        self._hover_shape: str | None = None    # hovered controller shape
        self._selected_input: str | None = None  # selected (red line) input
        self._show_borders: bool = False
        self._labels_locked: bool = False        # prevent label dragging
        self._hide_unassigned: bool = False      # hide inputs with no bindings
        self._dragging_from_panel: bool = False  # cross-widget drag active

        # Drag state
        self._dragging: str | None = None
        self._drag_start: tuple[float, float] = (0, 0)
        self._did_drag: bool = False

        # Drop target highlight (for drag-and-drop from action panel)
        self._drop_highlight_id: int | None = None
        self._dim_overlay_ids: list[int] = []   # grey overlays on incompatible inputs

        # Tooltip
        self._tooltip: tk.Toplevel | None = None

        # Per-label rumble icon PhotoImages (prevent GC)
        self._rumble_label_icons: list[ImageTk.PhotoImage] = []

        self._canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._load_image()
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<Motion>", self._on_mouse_move)
        self._canvas.bind("<Button-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", self._on_right_click)
        self._canvas.bind("<Leave>", self._on_leave)

    def _load_image(self):
        """Load the controller image (SVG preferred, PNG fallback)."""
        img_path = _find_image_path()

        if img_path.suffix == ".svg" and HAS_CAIROSVG:
            png_data = cairosvg.svg2png(
                url=str(img_path),
                output_width=744,
                output_height=500,
            )
            self._base_image = Image.open(io.BytesIO(png_data))
        else:
            png_path = img_path.with_suffix(".svg.png")
            if not png_path.exists():
                png_path = img_path
            self._base_image = Image.open(str(png_path))

        self._img_width = self._base_image.width
        self._img_height = self._base_image.height

        # Load rumble icon
        self._rumble_base_image = None
        rumble_path = _find_rumble_icon()
        if rumble_path:
            try:
                if rumble_path.suffix == ".svg" and HAS_CAIROSVG:
                    rumble_data = cairosvg.svg2png(
                        url=str(rumble_path),
                        output_width=64, output_height=64,
                    )
                    self._rumble_base_image = Image.open(
                        io.BytesIO(rumble_data)).convert("RGBA")
                elif rumble_path.suffix != ".svg":
                    self._rumble_base_image = Image.open(
                        str(rumble_path)).convert("RGBA")
            except Exception:
                pass  # Non-fatal: fallback icon is generated below
        # Fallback: draw a simple rumble icon with PIL if SVG couldn't load
        if self._rumble_base_image is None:
            self._rumble_base_image = self._make_rumble_fallback(64)

        # Load team gear logo for top-right overlay
        self._gear_base_image = None
        gear_path = _find_gear_icon()
        if gear_path:
            try:
                self._gear_base_image = Image.open(
                    str(gear_path)).convert("RGBA")
            except Exception:
                pass  # Non-fatal: gear overlay is optional decoration

    @staticmethod
    def _make_rumble_fallback(size: int) -> Image.Image:
        """Draw a simple rumble/vibration icon when SVG can't be loaded.

        Reproduces the key shapes from rumble.svg: a battery-like body
        with horizontal bars and a positive terminal nub.
        """
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        s = size / 24  # scale factor (SVG viewBox is 24x24)

        # Main body (rounded-ish rectangle: x=2..15, y=5..16)
        d.rectangle([s * 2, s * 5, s * 15, s * 16], fill=(0, 0, 0, 255))
        # Terminal nub (x=17..18, y=8..9.5 and x=17..22, y=9.5..11.5)
        d.rectangle([s * 17, s * 8, s * 18, s * 11.5], fill=(0, 0, 0, 255))
        d.rectangle([s * 17, s * 9.5, s * 22, s * 11.5], fill=(0, 0, 0, 255))
        # Inner bars (white gaps to show charge lines)
        for y_top in [7, 9, 11, 13]:
            d.rectangle([s * 5, s * y_top, s * 14, s * (y_top + 0.8),],
                        fill=(255, 255, 255, 255))
        # Base plate (x=3..16, y=17..19)
        d.rectangle([s * 3, s * 17, s * 16, s * 19], fill=(0, 0, 0, 255))
        return img

    def set_bindings(self, bindings: dict[str, list[str]]):
        """Update the displayed bindings and redraw."""
        self._bindings = dict(bindings)
        self._redraw()

    def set_show_borders(self, show: bool):
        """Toggle visibility of shape outlines and redraw."""
        self._show_borders = show
        self._redraw()

    def set_hide_unassigned(self, hide: bool):
        """Toggle hiding of inputs with no bindings and redraw."""
        self._hide_unassigned = hide
        self._redraw()

    def set_drag_cursor(self, dragging: bool):
        """Set cross-widget drag state so hover cursor is overridden."""
        self._dragging_from_panel = dragging
        self._canvas.config(cursor="plus" if dragging else "")

    def reset_label_positions(self):
        """Clear all custom label positions and redraw at defaults."""
        self._custom_label_pos.clear()
        self._redraw()

    def set_labels_locked(self, locked: bool):
        """Lock or unlock label dragging."""
        self._labels_locked = locked

    # --- Drop target highlighting (for drag-and-drop) ---

    def _root_to_canvas(self, x_root: int, y_root: int) -> tuple[int, int]:
        """Convert root screen coordinates to canvas-local coordinates."""
        return x_root - self._canvas.winfo_rootx(), y_root - self._canvas.winfo_rooty()

    def highlight_drop_target(self, x_root: int, y_root: int) -> str | None:
        """Highlight the binding box or shape under root coords.

        Returns the input name if over a single-input target, None otherwise.
        """
        self.clear_drop_highlight()
        cx, cy = self._root_to_canvas(x_root, y_root)

        # Check binding boxes first
        box_hit = self._hit_test_box(cx, cy)
        if box_hit and box_hit in self._box_items:
            box_id = self._box_items[box_hit][0]
            coords = self._canvas.coords(box_id)
            if len(coords) == 4:
                self._drop_highlight_id = self._canvas.create_rectangle(
                    coords[0] - 2, coords[1] - 2,
                    coords[2] + 2, coords[3] + 2,
                    outline="#2266cc", width=3, fill="",
                )
            return box_hit

        # Check shapes
        shape_hit = self._hit_test_shape(cx, cy)
        if shape_hit and shape_hit.name in self._shape_items:
            item_id = self._shape_items[shape_hit.name]
            coords = self._canvas.coords(item_id)
            if len(coords) == 4:
                self._drop_highlight_id = self._canvas.create_rectangle(
                    coords[0] - 2, coords[1] - 2,
                    coords[2] + 2, coords[3] + 2,
                    outline="#2266cc", width=3, fill="",
                )
            if len(shape_hit.inputs) == 1:
                return shape_hit.inputs[0]
            # Multi-input shape: caller should handle via get_drop_target
            return None

        return None

    def get_drop_target(self, x_root: int, y_root: int):
        """Return (input_name, shape) at root coordinates for drop resolution.

        Returns:
            (str, None) if over a binding box (direct single-input target)
            (str, None) if over a single-input shape
            (None, ButtonShape) if over a multi-input shape (caller shows menu)
            (None, None) if not over anything
        """
        cx, cy = self._root_to_canvas(x_root, y_root)

        box_hit = self._hit_test_box(cx, cy)
        if box_hit:
            return box_hit, None

        shape_hit = self._hit_test_shape(cx, cy)
        if shape_hit:
            if len(shape_hit.inputs) == 1:
                return shape_hit.inputs[0], None
            return None, shape_hit

        return None, None

    def clear_drop_highlight(self):
        """Remove any drop target highlighting."""
        if self._drop_highlight_id is not None:
            self._canvas.delete(self._drop_highlight_id)
            self._drop_highlight_id = None

    def dim_incompatible_inputs(self, compatible_names: set[str]):
        """Grey out incompatible boxes and highlight compatible ones.

        Also shows green outlines on controller button shapes that
        contain at least one compatible input.
        """
        self.clear_dim_overlays()
        # Highlight/dim binding boxes
        for name, item_ids in self._box_items.items():
            if not item_ids:
                continue
            box_id = item_ids[0]
            coords = self._canvas.coords(box_id)
            if len(coords) != 4:
                continue
            if name in compatible_names:
                # Green highlight border around compatible inputs
                oid = self._canvas.create_rectangle(
                    coords[0] - 3, coords[1] - 3,
                    coords[2] + 3, coords[3] + 3,
                    outline="#33aa33", width=3, fill="",
                )
                self._dim_overlay_ids.append(oid)
            else:
                # Solid grey overlay on incompatible inputs
                oid = self._canvas.create_rectangle(
                    coords[0], coords[1], coords[2], coords[3],
                    fill="#bbbbbb", outline="#999999", stipple="gray75",
                )
                self._dim_overlay_ids.append(oid)

        # Green outlines on compatible button shapes
        for shape_name, shape in self._shape_map.items():
            has_compatible = any(
                inp in compatible_names for inp in shape.inputs)
            if not has_compatible:
                continue
            item_id = self._shape_items.get(shape_name)
            if item_id is None:
                continue
            coords = self._canvas.coords(item_id)
            if len(coords) != 4:
                continue
            cx = (coords[0] + coords[2]) / 2
            cy = (coords[1] + coords[3]) / 2
            hw = (coords[2] - coords[0]) / 2
            hh = (coords[3] - coords[1]) / 2
            if shape.shape in ("circle", "pill"):
                oid = self._canvas.create_oval(
                    cx - hw, cy - hh, cx + hw, cy + hh,
                    outline="#33aa33", width=3, fill="",
                )
            else:
                oid = self._canvas.create_rectangle(
                    cx - hw, cy - hh, cx + hw, cy + hh,
                    outline="#33aa33", width=3, fill="",
                )
            self._dim_overlay_ids.append(oid)

    def clear_dim_overlays(self):
        """Remove drag compatibility overlays."""
        for oid in self._dim_overlay_ids:
            self._canvas.delete(oid)
        self._dim_overlay_ids.clear()

    def _on_resize(self, event):
        self._redraw()

    def _redraw(self):
        """Redraw the entire canvas: image, shapes, lines, and binding boxes."""
        self._canvas.delete("all")
        self._box_items.clear()
        self._line_items.clear()
        self._shape_items.clear()
        self._shape_map.clear()
        self._hover_shape = None
        self._rumble_label_icons.clear()
        self._label_icon_refs.clear()

        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            return

        # Scale image to fit canvas with proportional padding for labels.
        # Reserve a fraction of canvas width for label columns on each side
        # so the controller image fills more space as the window shrinks.
        pad_frac = 0.12  # fraction of canvas width reserved per side
        pad_x = max(50, int(canvas_w * pad_frac))
        pad_top = max(20, int(canvas_h * 0.04))
        pad_bot = max(50, int(canvas_h * 0.10))  # extra bottom room for Mac DPI scaling
        avail_w = canvas_w - 2 * pad_x
        avail_h = canvas_h - pad_top - pad_bot

        scale = min(avail_w / self._img_width, avail_h / self._img_height)
        scale = max(scale, 0.08)
        scale = min(scale, 1.5)

        new_w = int(self._img_width * scale)
        new_h = int(self._img_height * scale)

        resized = self._base_image.resize((new_w, new_h), Image.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(resized)

        # Center horizontally, shift down slightly to leave room for
        # rumble icons above the controller and reduce bottom whitespace.
        img_x = canvas_w // 2
        img_y = int(canvas_h * 0.51)
        self._bg_image_id = self._canvas.create_image(
            img_x, img_y, image=self._tk_image, anchor=tk.CENTER)

        # Store rendered image bounds for fractional coordinate mapping
        self._img_left = img_x - new_w // 2
        self._img_top = img_y - new_h // 2
        self._rendered_w = new_w
        self._rendered_h = new_h

        # Compute scaled label sizes based on image scale
        self._compute_scaled_sizes(scale)

        # Draw button outlines on the controller
        for shape in XBOX_SHAPES:
            self._draw_shape(shape)

        # Draw lines and binding boxes for each input
        self._group_stack_index: dict[str, int] = {}
        self._group_stack_origin: dict[str, tuple[float, float]] = {}
        for inp in XBOX_INPUTS:
            if self._hide_unassigned and not self._bindings.get(inp.name):
                continue
            self._draw_input(inp)

        # Draw connector bars for grouped labels (D-pad, sticks)
        self._draw_connector_groups()

        # Draw rumble icons below each rumble label box
        self._draw_rumble_icons()

        # Draw team logo in top-right corner
        self._draw_gear_logo(canvas_w)

        # Re-apply selection highlight after redraw
        if self._selected_input and self._selected_input in self._line_items:
            self._canvas.itemconfig(
                self._line_items[self._selected_input],
                fill=LINE_SELECTED_COLOR, width=2)

    # Label sizes are designed for scale ~0.4-0.5 (typical canvas).
    # This multiplier bumps them up so they're readable at normal zoom.
    _LABEL_SCALE_BOOST = 1.75

    def _compute_scaled_sizes(self, img_scale: float):
        """Recompute all label dimensions from the current image scale.

        Reference sizes are defined for scale=1.0 (image at native res).
        Everything scales linearly so labels shrink/grow with the canvas.
        """
        s = max(img_scale * self._LABEL_SCALE_BOOST * self._dpi_scale, 0.25)
        self._s = s
        self._box_w = max(100, int(_REF_BOX_WIDTH * s))
        self._box_h = max(22, int(_REF_BOX_HEIGHT * s))
        self._box_pad = max(3, int(_REF_BOX_PAD * s))
        self._label_font_size = max(8, int(_REF_LABEL_FONT * s))
        self._action_font_size = max(9, int(_REF_ACTION_FONT * s))
        self._plus_font_size = max(12, int(_REF_PLUS_FONT * s))
        self._label_y_offset = max(12, int(_REF_LABEL_Y * s))
        self._action_step = max(14, int(_REF_ACTION_STEP * s))
        self._icon_size = max(10, self._box_h - int(8 * s))

    def _map_frac(self, frac_x: float, frac_y: float) -> tuple[float, float]:
        """Map fractional image coordinates (0-1) to canvas pixel position."""
        return (
            self._img_left + frac_x * self._rendered_w,
            self._img_top + frac_y * self._rendered_h,
        )

    def _unmap_to_img(self, cx: float, cy: float) -> tuple[int, int]:
        """Convert canvas pixel position back to source image pixel coords."""
        frac_x = (cx - self._img_left) / self._rendered_w if self._rendered_w else 0
        frac_y = (cy - self._img_top) / self._rendered_h if self._rendered_h else 0
        return int(frac_x * _IMG_W), int(frac_y * _IMG_H)

    def _map_label(self, inp: InputCoord, canvas_w: int,
                   canvas_h: int) -> tuple[float, float]:
        """Map label positions.  Uses custom dragged position if available,
        otherwise places at the left or right canvas edge."""
        bw = self._box_w
        bh = self._box_h
        if inp.name in self._custom_label_pos:
            img_x, img_y = self._custom_label_pos[inp.name]
            lx = self._img_left + (img_x / _IMG_W) * self._rendered_w
            ly = self._img_top + (img_y / _IMG_H) * self._rendered_h
            lx = max(5, min(lx, canvas_w - bw - 5))
            ly = max(5, min(ly, canvas_h - bh - 5))
            return lx, ly

        lx = self._img_left + inp.label_x * self._rendered_w
        ly = self._img_top + inp.label_y * self._rendered_h
        lx = max(5, min(lx, canvas_w - bw - 5))
        ly = max(5, min(ly, canvas_h - bh - 5))
        return lx, ly

    # --- Connector bars for grouped inputs ---

    # Groups of inputs that share a single leader line + vertical bar.
    # Each entry: (prefix to match, anchor input for the leader line)
    _CONNECTOR_GROUPS = [
        ("pov_", "pov_right"),           # D-pad
        ("left_stick", "left_stick_x"),  # Left stick
        ("right_stick", "right_stick_x"),  # Right stick
    ]

    def _get_drag_group(self, name: str) -> list[str]:
        """Return all names in the same connector group, or just [name]."""
        for prefix, _ in self._CONNECTOR_GROUPS:
            if name.startswith(prefix):
                return [n for n in self._box_items if n.startswith(prefix)]
        return [name]

    def _draw_connector_groups(self):
        """Draw connector bars for grouped label columns.

        Each group gets a vertical bar along the right edge of its label
        column, with a single leader line from the shared anchor point
        to the bar midpoint.  Items are stored in ``_connector_group_items``
        so they can be updated during drag.
        """
        from .layout_coords import XBOX_INPUT_MAP

        self._connector_group_items: dict[str, tuple[int, int]] = {}

        for prefix, anchor_name in self._CONNECTOR_GROUPS:
            boxes = []
            for name, item_ids in self._box_items.items():
                if name.startswith(prefix) and item_ids:
                    coords = self._canvas.coords(item_ids[0])
                    if len(coords) == 4:
                        boxes.append(coords)
            if not boxes:
                continue

            right_x = max(c[2] for c in boxes)
            top_y = min(c[1] for c in boxes)
            bottom_y = max(c[3] for c in boxes)
            bar_x = right_x + 6

            # Vertical bar
            bar_id = self._canvas.create_line(
                bar_x, top_y, bar_x, bottom_y,
                fill=LINE_COLOR, width=3,
            )

            # Leader line from anchor to bar midpoint
            line_id = None
            anchor_inp = XBOX_INPUT_MAP.get(anchor_name)
            if anchor_inp:
                ax, ay = self._map_frac(anchor_inp.anchor_x,
                                        anchor_inp.anchor_y)
                bar_mid_y = (top_y + bottom_y) / 2
                line_id = self._canvas.create_line(
                    ax, ay, bar_x, bar_mid_y,
                    fill=LINE_COLOR, width=1,
                )

            self._connector_group_items[prefix] = (bar_id, line_id)

    def _update_connector_group(self, prefix: str):
        """Reposition the connector bar and leader line for a group."""
        from .layout_coords import XBOX_INPUT_MAP

        items = self._connector_group_items.get(prefix)
        if not items:
            return
        bar_id, line_id = items

        boxes = []
        for name, item_ids in self._box_items.items():
            if name.startswith(prefix) and item_ids:
                coords = self._canvas.coords(item_ids[0])
                if len(coords) == 4:
                    boxes.append(coords)
        if not boxes:
            return

        right_x = max(c[2] for c in boxes)
        top_y = min(c[1] for c in boxes)
        bottom_y = max(c[3] for c in boxes)
        bar_x = right_x + 6

        self._canvas.coords(bar_id, bar_x, top_y, bar_x, bottom_y)

        if line_id:
            anchor_name = None
            for p, a in self._CONNECTOR_GROUPS:
                if p == prefix:
                    anchor_name = a
                    break
            anchor_inp = XBOX_INPUT_MAP.get(anchor_name) if anchor_name else None
            if anchor_inp:
                ax, ay = self._map_frac(anchor_inp.anchor_x,
                                        anchor_inp.anchor_y)
                bar_mid_y = (top_y + bottom_y) / 2
                self._canvas.coords(line_id, ax, ay, bar_x, bar_mid_y)

    # --- Rumble icons ---

    def _draw_rumble_icons(self):
        """Draw a rumble icon on the controller at each rumble anchor."""
        from .layout_coords import XBOX_INPUT_MAP
        if not self._rumble_base_image:
            return
        icon_size = self._box_w // 4
        resized = self._rumble_base_image.resize(
            (icon_size, icon_size), Image.LANCZOS)

        for name in ["rumble_left", "rumble_both", "rumble_right"]:
            inp = XBOX_INPUT_MAP.get(name)
            if not inp:
                continue
            cx, cy = self._map_frac(inp.anchor_x, inp.anchor_y)
            tk_icon = ImageTk.PhotoImage(resized)
            self._rumble_label_icons.append(tk_icon)
            self._canvas.create_image(
                cx, cy, image=tk_icon, anchor=tk.CENTER)

    # --- Gear logo ---

    def _draw_gear_logo(self, canvas_w: int):
        """Draw the team gear logo in the top-right corner of the canvas."""
        if not self._gear_base_image:
            return
        # ~96px (approx 1 inch at standard DPI)
        logo_size = 96
        resized = self._gear_base_image.resize(
            (logo_size, logo_size), Image.LANCZOS)
        self._gear_tk_image = ImageTk.PhotoImage(resized)
        margin = 8
        self._canvas.create_image(
            canvas_w - margin, margin,
            image=self._gear_tk_image, anchor=tk.NE)

    # --- Shape drawing ---

    def _draw_shape(self, shape: ButtonShape):
        """Draw a bold outline on the controller for a button/stick/trigger."""
        cx, cy = self._map_frac(shape.center_x, shape.center_y)
        hw = shape.width * self._rendered_w / 2
        hh = shape.height * self._rendered_h / 2

        outline = SHAPE_OUTLINE_COLOR if self._show_borders else ""
        width = SHAPE_OUTLINE_WIDTH if self._show_borders else 0

        if shape.shape == "circle":
            item = self._canvas.create_oval(
                cx - hw, cy - hh, cx + hw, cy + hh,
                outline=outline, width=width,
                fill="",
            )
        elif shape.shape == "pill":
            # Rounded rectangle approximation using an oval
            item = self._canvas.create_oval(
                cx - hw, cy - hh, cx + hw, cy + hh,
                outline=outline, width=width,
                fill="",
            )
        else:  # rect
            item = self._canvas.create_rectangle(
                cx - hw, cy - hh, cx + hw, cy + hh,
                outline=outline, width=width,
                fill="",
            )

        self._shape_items[shape.name] = item
        self._shape_map[shape.name] = shape

    # --- Binding box drawing ---

    # D-pad inputs are stacked in canvas-pixel space so spacing is
    # consistent regardless of zoom level.
    _STACK_GROUPS = {"pov_"}

    def _draw_input(self, inp: InputCoord):
        """Draw a single input's leader line and binding box."""
        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()

        # Scaled sizes
        bw = self._box_w
        bh = self._box_h
        bp = self._box_pad
        lf = self._label_font_size
        af = self._action_font_size
        pf = self._plus_font_size
        ly_off = self._label_y_offset
        a_step = self._action_step
        ic_sz = self._icon_size

        ax, ay = self._map_frac(inp.anchor_x, inp.anchor_y)
        lx, ly = self._map_label(inp, canvas_w, canvas_h)

        # Stack grouped labels at fixed canvas-pixel intervals
        for prefix in self._STACK_GROUPS:
            if inp.name.startswith(prefix):
                if prefix not in self._group_stack_origin:
                    self._group_stack_origin[prefix] = (lx, ly)
                    self._group_stack_index[prefix] = 0
                else:
                    idx = self._group_stack_index[prefix] + 1
                    self._group_stack_index[prefix] = idx
                    origin_x, origin_y = self._group_stack_origin[prefix]
                    lx = origin_x
                    ly = origin_y + idx * bh
                break

        box_cx = lx + bw / 2
        box_cy = ly + bh / 2

        # Leader line — skip for grouped inputs (connector bar drawn separately)
        is_grouped = (inp.name.startswith("pov_")
                      or inp.name.startswith("left_stick")
                      or inp.name.startswith("right_stick"))
        if not is_grouped:
            line_id = self._canvas.create_line(
                ax, ay, box_cx, box_cy,
                fill=LINE_COLOR, width=1,
            )
            self._line_items[inp.name] = line_id

        # Assigned actions — D-pad single-line, sticks max 2
        actions = self._bindings.get(inp.name, [])
        is_dpad = inp.name.startswith("pov_")
        is_stick = (inp.name.startswith("left_stick")
                    or inp.name.startswith("right_stick"))
        all_actions = actions
        if is_dpad:
            actions = all_actions[:1]
        elif is_stick:
            actions = all_actions[:2]
        has_actions = len(all_actions) > 0
        fill = BOX_FILL_ASSIGNED if has_actions else BOX_FILL
        if is_dpad:
            total_height = bh
        elif has_actions:
            total_height = ly_off + len(actions) * a_step
        else:
            total_height = bh

        # Box background
        box_id = self._canvas.create_rectangle(
            lx, ly, lx + bw, ly + total_height,
            fill=fill, outline=BOX_OUTLINE, width=1,
        )

        axis_tag = None
        if inp.name.endswith("_x"):
            axis_tag = "X"
        elif inp.name.endswith("_y"):
            axis_tag = "Y"

        items = [box_id]

        # Input icon (scaled)
        text_offset = bp
        if self._icon_loader:
            icon = self._icon_loader.get_tk_icon(inp.name, ic_sz)
            if icon:
                self._label_icon_refs.append(icon)
                icon_id = self._canvas.create_image(
                    lx + bp, ly + 1, image=icon, anchor=tk.NW)
                items.append(icon_id)
                text_offset = bp + ic_sz + max(2, int(4 * self._s))

        # Input label
        label_color = (AXIS_INDICATOR_COLORS[axis_tag]
                       if axis_tag else "#555555")

        if is_dpad:
            # D-pad compact: icon + label + action on one line
            line_text = inp.display_name
            if has_actions:
                line_text += " : " + actions[0]
            label_id = self._canvas.create_text(
                lx + text_offset, ly + 2,
                text=line_text, anchor=tk.NW,
                font=("Arial", lf, "bold" if has_actions else ""),
                fill=ASSIGNED_COLOR if has_actions else label_color,
            )
            items.append(label_id)
            # "+" indicator when extra bindings are hidden
            if has_actions and len(all_actions) > 1:
                plus_id = self._canvas.create_text(
                    lx + bw + max(2, int(4 * self._s)), ly - int(4 * self._s),
                    text="+", anchor=tk.NW,
                    font=("Arial", pf, "bold"), fill=ASSIGNED_COLOR,
                )
                items.append(plus_id)
        else:
            label_id = self._canvas.create_text(
                lx + text_offset, ly + 2,
                text=inp.display_name, anchor=tk.NW,
                font=("Arial", lf), fill=label_color,
            )
            items.append(label_id)

            # Action names or unassigned text
            if has_actions:
                for i, action in enumerate(actions):
                    txt_id = self._canvas.create_text(
                        lx + bp, ly + ly_off + i * a_step,
                        text=action, anchor=tk.NW,
                        font=("Arial", af, "bold"), fill=ASSIGNED_COLOR,
                    )
                    items.append(txt_id)
                # "+" when actions are truncated (sticks capped at 2)
                if len(all_actions) > len(actions):
                    plus_id = self._canvas.create_text(
                        lx + bw + max(2, int(4 * self._s)),
                        ly - int(4 * self._s),
                        text="+", anchor=tk.NW,
                        font=("Arial", pf, "bold"), fill=ASSIGNED_COLOR,
                    )
                    items.append(plus_id)
            else:
                txt_id = self._canvas.create_text(
                    lx + bp, ly + ly_off,
                    text=UNASSIGNED_TEXT, anchor=tk.NW,
                    font=("Arial", af), fill=UNASSIGNED_COLOR,
                )
                items.append(txt_id)

        self._box_items[inp.name] = items

    # --- Hit testing ---

    def _hit_test_box(self, x: float, y: float) -> str | None:
        """Return input name if (x, y) is inside a binding box."""
        for name, item_ids in self._box_items.items():
            if not item_ids:
                continue
            box_id = item_ids[0]
            coords = self._canvas.coords(box_id)
            if len(coords) == 4:
                x1, y1, x2, y2 = coords
                if x1 <= x <= x2 and y1 <= y <= y2:
                    return name
        return None

    def _hit_test_shape(self, x: float, y: float) -> ButtonShape | None:
        """Return the ButtonShape if (x, y) is inside a controller outline."""
        for shape_name, item_id in self._shape_items.items():
            coords = self._canvas.coords(item_id)
            if len(coords) == 4:
                x1, y1, x2, y2 = coords
                shape = self._shape_map[shape_name]
                if shape.shape == "circle":
                    # Ellipse hit test
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    rx = (x2 - x1) / 2
                    ry = (y2 - y1) / 2
                    if rx > 0 and ry > 0:
                        if ((x - cx) ** 2 / rx ** 2
                                + (y - cy) ** 2 / ry ** 2) <= 1:
                            return shape
                else:
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        return shape
        return None

    # --- Selection ---

    def clear_selection(self):
        """Clear the selected input, restoring line to default color."""
        self._select_input(None)

    def _select_input(self, name: str | None):
        """Set the selected input, updating line colors."""
        # Deselect previous
        if (self._selected_input
                and self._selected_input in self._line_items):
            self._canvas.itemconfig(
                self._line_items[self._selected_input],
                fill=LINE_COLOR, width=1)
        # Select new
        self._selected_input = name
        if name and name in self._line_items:
            line_id = self._line_items[name]
            self._canvas.itemconfig(
                line_id, fill=LINE_SELECTED_COLOR, width=2)
            # Ensure line is visible above the background image
            if hasattr(self, '_bg_image_id'):
                self._canvas.tag_raise(line_id, self._bg_image_id)

    # --- Drag helpers ---

    def _move_box(self, name: str, dx: float, dy: float):
        """Move all canvas items for a binding box by (dx, dy)."""
        for item_id in self._box_items.get(name, []):
            self._canvas.move(item_id, dx, dy)

    def _update_line_for_box(self, name: str):
        """Recreate the leader line to the current box center position."""
        if name not in self._line_items or name not in self._box_items:
            return
        from .layout_coords import XBOX_INPUT_MAP
        inp = XBOX_INPUT_MAP.get(name)
        if not inp:
            return

        # Anchor point on the controller image
        ax, ay = self._map_frac(inp.anchor_x, inp.anchor_y)

        # Current box center
        box_coords = self._canvas.coords(self._box_items[name][0])
        if len(box_coords) != 4:
            return
        box_cx = (box_coords[0] + box_coords[2]) / 2
        box_cy = (box_coords[1] + box_coords[3]) / 2

        # Delete old line and create new
        old_line = self._line_items[name]
        self._canvas.delete(old_line)

        is_selected = (name == self._selected_input)
        color = LINE_SELECTED_COLOR if is_selected else LINE_COLOR
        width = 2 if is_selected else 1

        new_line = self._canvas.create_line(
            ax, ay, box_cx, box_cy,
            fill=color, width=width,
        )
        self._line_items[name] = new_line
        # Place line above the background image but below boxes/shapes
        self._canvas.tag_raise(new_line, self._bg_image_id)

    # --- Tooltip ---

    @staticmethod
    def _input_description(inp: InputCoord) -> str:
        """Build a one-line type description for an input."""
        if inp.input_type == "axis":
            if inp.name.endswith("_x"):
                return "X Axis float [-1 (Left), 1 (Right)]"
            elif inp.name.endswith("_y"):
                return "Y Axis float [-1 (Up), 1 (Down)]"
            else:
                return "Axis float [0 (Released), 1 (Pressed)]"
        elif inp.name.startswith("pov_"):
            pov_degrees = {
                "pov_up": 0, "pov_up_right": 45,
                "pov_right": 90, "pov_down_right": 135,
                "pov_down": 180, "pov_down_left": 225,
                "pov_left": 270, "pov_up_left": 315,
            }
            deg = pov_degrees.get(inp.name, "?")
            return f"D-Pad [{deg}\u00b0, Button]"
        elif inp.input_type == "output":
            return "Output float [0.0 (Off), 1.0 (Max)]"
        else:
            return "Button [Boolean]"

    def _build_tooltip_text(self, shape: ButtonShape) -> str:
        """Build multi-line tooltip text for a controller shape."""
        from .layout_coords import XBOX_INPUT_MAP

        # Title from the shape's first input's common name
        title_map = {
            "ls": "Left Analog Stick", "rs": "Right Analog Stick",
            "lt": "Left Trigger", "rt": "Right Trigger",
            "lb": "Left Bumper", "rb": "Right Bumper",
            "a": "A Button", "b": "B Button",
            "x": "X Button", "y": "Y Button",
            "back": "Back Button", "start": "Start Button",
            "dpad": "D-Pad",
            "rumble_l": "Left Rumble", "rumble_b": "Both Rumble",
            "rumble_r": "Right Rumble",
        }
        title = title_map.get(shape.name, shape.name)
        lines = [title]
        for input_name in shape.inputs:
            inp = XBOX_INPUT_MAP.get(input_name)
            if inp:
                lines.append(f"  {inp.display_name}: {self._input_description(inp)}")
        return "\n".join(lines)

    def _show_tooltip(self, x_root: int, y_root: int, text: str):
        """Show or update the tooltip near the cursor."""
        if self._tooltip:
            label = self._tooltip.winfo_children()[0]
            label.config(text=text)
            self._tooltip.geometry(f"+{x_root + 15}+{y_root + 10}")
            self._tooltip.deiconify()
            return

        self._tooltip = tw = tk.Toplevel(self)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x_root + 15}+{y_root + 10}")
        tw.attributes("-topmost", True)
        label = tk.Label(
            tw, text=text, justify=tk.LEFT,
            background="#ffffe0", foreground="#222222",
            relief=tk.SOLID, borderwidth=1,
            font=("Arial", 9), padx=6, pady=4,
        )
        label.pack()

    def _hide_tooltip(self):
        """Hide the tooltip."""
        if self._tooltip:
            self._tooltip.withdraw()

    # --- Event handlers ---

    def _on_mouse_move(self, event):
        """Highlight binding boxes and controller shapes on hover."""
        # Skip hover highlighting while dragging
        if self._dragging:
            return

        # Check binding boxes first (they're on top)
        box_hit = self._hit_test_box(event.x, event.y)
        shape_hit = self._hit_test_shape(event.x, event.y)

        # Update binding box highlight
        if box_hit != self._hover_input:
            # Unhighlight previous hover box
            if self._hover_input and self._hover_input in self._box_items:
                items = self._box_items[self._hover_input]
                if items:
                    has_actions = bool(
                        self._bindings.get(self._hover_input))
                    fill = BOX_FILL_ASSIGNED if has_actions else BOX_FILL
                    self._canvas.itemconfig(items[0], fill=fill)
                # Restore line color unless this input is selected
                if (self._hover_input != self._selected_input
                        and self._hover_input in self._line_items):
                    self._canvas.itemconfig(
                        self._line_items[self._hover_input],
                        fill=LINE_COLOR, width=1)

            # Highlight new hover box
            if box_hit and box_hit in self._box_items:
                items = self._box_items[box_hit]
                if items:
                    self._canvas.itemconfig(items[0], fill=BOX_FILL_HOVER)
                # Turn line red on hover
                if box_hit in self._line_items:
                    self._canvas.itemconfig(
                        self._line_items[box_hit],
                        fill=LINE_SELECTED_COLOR, width=2)

            self._hover_input = box_hit

            # Notify parent of hovered input change
            if self._on_hover_input:
                self._on_hover_input(box_hit)

        # Update shape highlight
        new_shape_name = shape_hit.name if shape_hit else None
        if new_shape_name != self._hover_shape:
            # Unhighlight previous shape
            if self._hover_shape and self._hover_shape in self._shape_items:
                item_id = self._shape_items[self._hover_shape]
                rest_outline = SHAPE_OUTLINE_COLOR if self._show_borders else ""
                rest_width = SHAPE_OUTLINE_WIDTH if self._show_borders else 0
                self._canvas.itemconfig(
                    item_id, outline=rest_outline, width=rest_width)

            # Highlight new shape (always show on hover)
            if new_shape_name and new_shape_name in self._shape_items:
                item_id = self._shape_items[new_shape_name]
                self._canvas.itemconfig(
                    item_id, outline="#2266aa", width=SHAPE_OUTLINE_WIDTH + 1.5)

            self._hover_shape = new_shape_name

            # Notify parent of hovered shape change
            if self._on_hover_shape:
                if shape_hit:
                    self._on_hover_shape(list(shape_hit.inputs))
                else:
                    self._on_hover_shape(None)

        # Tooltip for shapes
        if shape_hit and not box_hit:
            text = self._build_tooltip_text(shape_hit)
            self._show_tooltip(event.x_root, event.y_root, text)
        else:
            self._hide_tooltip()

        # Cursor (don't override plus cursor during cross-widget drag)
        if not self._dragging_from_panel:
            if box_hit or shape_hit:
                self._canvas.config(cursor="hand2")
            else:
                self._canvas.config(cursor="")

        # Report image-space coordinates to parent
        if self._on_mouse_coord and hasattr(self, '_rendered_w'):
            img_x, img_y = self._unmap_to_img(event.x, event.y)
            self._on_mouse_coord(img_x, img_y)

    def _on_leave(self, event):
        """Hide tooltip when the cursor leaves the canvas."""
        self._hide_tooltip()

    def _on_press(self, event):
        """Handle mouse button press — start potential drag or shape click."""
        box_hit = self._hit_test_box(event.x, event.y)
        if box_hit:
            self._dragging = box_hit
            self._drag_start = (event.x, event.y)
            self._did_drag = False
            self._select_input(box_hit)
            return

        # If not on a box, clear drag state
        self._dragging = None
        self._did_drag = False

    def _on_drag(self, event):
        """Handle mouse drag — move binding box if dragging."""
        if not self._dragging or self._labels_locked:
            return

        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]

        if not self._did_drag:
            dist = math.hypot(dx, dy)
            if dist < _DRAG_THRESHOLD:
                return
            self._did_drag = True
            self._canvas.config(cursor="fleur")

        # Move the box items — group drag for connected labels
        group_names = self._get_drag_group(self._dragging)
        for gname in group_names:
            self._move_box(gname, dx, dy)
            self._update_line_for_box(gname)

        # Update connector bar/line for the dragged group
        for prefix, _ in self._CONNECTOR_GROUPS:
            if self._dragging.startswith(prefix):
                self._update_connector_group(prefix)
                break

        self._drag_start = (event.x, event.y)

    def _on_release(self, event):
        """Handle mouse button release — finish drag or fire click."""
        name = self._dragging
        self._dragging = None

        if name and self._did_drag:
            # Drag finished — save positions for all group members
            for gname in self._get_drag_group(name):
                box_items = self._box_items.get(gname, [])
                if box_items:
                    coords = self._canvas.coords(box_items[0])
                    if len(coords) == 4:
                        lx, ly = coords[0], coords[1]
                        img_x, img_y = self._unmap_to_img(lx, ly)
                        self._custom_label_pos[gname] = (img_x, img_y)
                        if self._on_label_moved:
                            self._on_label_moved(gname, img_x, img_y)
            self._canvas.config(cursor="hand2")
            self._did_drag = False
            return

        self._did_drag = False

        # Was a click (no drag) — handle binding click or shape click
        if name:
            # Clicked on a binding box
            if self._on_binding_click:
                self._on_binding_click(name)
            return

        # Check shapes (click wasn't on a box)
        shape_hit = self._hit_test_shape(event.x, event.y)
        if shape_hit and self._on_binding_click:
            if len(shape_hit.inputs) == 1:
                self._select_input(shape_hit.inputs[0])
                self._on_binding_click(shape_hit.inputs[0])
            else:
                self._show_input_menu(event, shape_hit)

    def _on_right_click(self, event):
        """Show a context menu for clearing actions on right-click.

        Works on binding boxes (labels) and controller shapes (buttons).
        Shows individual action removal items plus Clear All.
        """
        box_hit = self._hit_test_box(event.x, event.y)
        if box_hit:
            self._show_binding_context_menu(event, box_hit)
            return

        shape_hit = self._hit_test_shape(event.x, event.y)
        if shape_hit:
            self._show_shape_context_menu(event, shape_hit)

    def _show_binding_context_menu(self, event, input_name: str):
        """Context menu for a binding box: remove individual actions + clear all."""
        self._select_input(input_name)
        actions = self._bindings.get(input_name, [])
        menu = tk.Menu(self._canvas, tearoff=0)

        if actions:
            for action in actions:
                menu.add_command(
                    label=f"Remove: {action}",
                    command=lambda n=input_name, a=action:
                        self._on_action_remove(n, a)
                        if self._on_action_remove else None,
                )
            menu.add_separator()
            menu.add_command(
                label="Clear All",
                command=lambda n=input_name: self._on_binding_clear(n)
                        if self._on_binding_clear else None,
            )
        else:
            menu.add_command(label="(no actions bound)", state=tk.DISABLED)

        menu.tk_popup(event.x_root, event.y_root)

    def _show_shape_context_menu(self, event, shape: ButtonShape):
        """Context menu for a controller shape: remove individual actions + clear all."""
        from .layout_coords import XBOX_INPUT_MAP

        menu = tk.Menu(self._canvas, tearoff=0)
        has_any = False

        for input_name in shape.inputs:
            actions = self._bindings.get(input_name, [])
            if not actions:
                continue
            has_any = True
            inp = XBOX_INPUT_MAP.get(input_name)
            display = inp.display_name if inp else input_name
            for action in actions:
                menu.add_command(
                    label=f"Remove: {action} ({display})",
                    command=lambda n=input_name, a=action:
                        self._on_action_remove(n, a)
                        if self._on_action_remove else None,
                )

        if has_any:
            menu.add_separator()
            menu.add_command(
                label="Clear All",
                command=lambda: self._clear_shape_bindings(shape),
            )
        else:
            menu.add_command(label="(no actions bound)", state=tk.DISABLED)

        menu.tk_popup(event.x_root, event.y_root)

    def _clear_shape_bindings(self, shape: ButtonShape):
        """Clear bindings for all inputs of a shape."""
        if not self._on_binding_clear:
            return
        for input_name in shape.inputs:
            if self._bindings.get(input_name):
                self._on_binding_clear(input_name)

    def _show_input_menu(self, event, shape: ButtonShape):
        """Show a context menu to pick which input to configure
        when a shape maps to multiple inputs (e.g., stick X/Y/button)."""
        from .layout_coords import XBOX_INPUT_MAP

        menu = tk.Menu(self._canvas, tearoff=0)
        for input_name in shape.inputs:
            inp = XBOX_INPUT_MAP.get(input_name)
            display = inp.display_name if inp else input_name
            # Capture input_name in the lambda default arg
            menu.add_command(
                label=display,
                command=lambda n=input_name: self._on_binding_click(n),
            )
        menu.tk_popup(event.x_root, event.y_root)
