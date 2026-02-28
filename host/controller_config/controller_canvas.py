"""Canvas widget that renders the Xbox controller image with binding overlays.

Draws leader lines from each controller input to binding boxes showing
assigned actions. Clicking a binding box triggers the binding dialog.
"""

import io
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from .layout_coords import XBOX_INPUTS, InputCoord

# Try cairosvg for crisp SVG rendering, fall back to pre-rendered PNG
try:
    import cairosvg
    HAS_CAIROSVG = True
except (ImportError, OSError):
    HAS_CAIROSVG = False

# Visual constants
BOX_WIDTH = 120
BOX_HEIGHT = 22
BOX_PAD = 4
LINE_COLOR = "#555555"
BOX_OUTLINE = "#888888"
BOX_FILL = "#f0f0f0"
BOX_FILL_HOVER = "#ddeeff"
BOX_FILL_ASSIGNED = "#d4edda"
UNASSIGNED_TEXT = "(unassigned)"
UNASSIGNED_COLOR = "#999999"
ASSIGNED_COLOR = "#222222"
AXIS_INDICATOR_COLORS = {"X": "#cc4444", "Y": "#4444cc"}


def _find_image_path() -> Path:
    """Locate the Xbox controller image relative to the project root."""
    # Walk up from this file to find the project images/ folder
    here = Path(__file__).resolve().parent
    for ancestor in [here, here.parent, here.parent.parent]:
        svg_path = ancestor / "images" / "Xbox_Controller.svg"
        if svg_path.exists():
            return svg_path
        png_path = ancestor / "images" / "Xbox_Controller.svg.png"
        if png_path.exists():
            return png_path
    raise FileNotFoundError("Cannot find Xbox_Controller image in images/")


class ControllerCanvas(tk.Frame):
    """Displays the Xbox controller with interactive binding boxes."""

    def __init__(self, parent, on_binding_click=None):
        """
        Args:
            parent: tkinter parent widget
            on_binding_click: callback(input_name: str) when a binding box is clicked
        """
        super().__init__(parent)
        self._on_binding_click = on_binding_click
        self._bindings: dict[str, list[str]] = {}
        self._box_items: dict[str, list[int]] = {}  # input_name -> canvas item ids
        self._hover_input: str | None = None

        self._canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._load_image()
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<Motion>", self._on_mouse_move)
        self._canvas.bind("<Button-1>", self._on_click)

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
            # Use PNG fallback
            png_path = img_path.with_suffix(".svg.png")
            if not png_path.exists():
                png_path = img_path
            self._base_image = Image.open(str(png_path))

        self._img_width = self._base_image.width
        self._img_height = self._base_image.height

    def set_bindings(self, bindings: dict[str, list[str]]):
        """Update the displayed bindings and redraw."""
        self._bindings = dict(bindings)
        self._redraw()

    def _on_resize(self, event):
        self._redraw()

    def _redraw(self):
        """Redraw the entire canvas: image, lines, and binding boxes."""
        self._canvas.delete("all")
        self._box_items.clear()

        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            return

        # Scale image to fit canvas with padding for labels
        pad_x = BOX_WIDTH + 30
        avail_w = canvas_w - 2 * pad_x
        avail_h = canvas_h - 40

        scale = min(avail_w / self._img_width, avail_h / self._img_height)
        scale = min(scale, 1.5)  # Don't upscale too much

        new_w = int(self._img_width * scale)
        new_h = int(self._img_height * scale)

        resized = self._base_image.resize((new_w, new_h), Image.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(resized)

        # Center the image
        img_x = canvas_w // 2
        img_y = canvas_h // 2
        self._canvas.create_image(img_x, img_y, image=self._tk_image, anchor=tk.CENTER)

        # Calculate offset for coordinate mapping
        self._offset_x = img_x - new_w // 2
        self._offset_y = img_y - new_h // 2
        self._scale = scale

        # Draw lines and binding boxes for each input
        for inp in XBOX_INPUTS:
            self._draw_input(inp)

    def _map_coord(self, svg_x: float, svg_y: float) -> tuple[float, float]:
        """Map SVG-space coordinates to canvas-space."""
        return (
            self._offset_x + svg_x * self._scale,
            self._offset_y + svg_y * self._scale,
        )

    def _map_label(self, inp: InputCoord, canvas_w: int, canvas_h: int) -> tuple[float, float]:
        """Map label positions, placing them at canvas edges."""
        # Labels on the left or right side
        if inp.label_x < 372:
            # Left side label
            lx = 10
        else:
            # Right side label
            lx = canvas_w - BOX_WIDTH - 10

        # Scale Y proportionally
        ly = self._offset_y + inp.label_y * self._scale
        # Clamp to canvas bounds
        ly = max(5, min(ly, canvas_h - BOX_HEIGHT - 5))
        return lx, ly

    def _draw_input(self, inp: InputCoord):
        """Draw a single input's leader line and binding box."""
        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()

        # Anchor point on the controller
        ax, ay = self._map_coord(inp.anchor_x, inp.anchor_y)
        # Label position at canvas edge
        lx, ly = self._map_label(inp, canvas_w, canvas_h)

        # Box center for line endpoint
        box_cx = lx + BOX_WIDTH / 2
        box_cy = ly + BOX_HEIGHT / 2

        # Draw leader line
        self._canvas.create_line(
            ax, ay, box_cx, box_cy,
            fill=LINE_COLOR, width=1, dash=(4, 2),
        )

        # Get assigned actions
        actions = self._bindings.get(inp.name, [])
        has_actions = len(actions) > 0

        # Determine box style
        fill = BOX_FILL_ASSIGNED if has_actions else BOX_FILL

        # Calculate box height based on number of actions
        total_height = max(BOX_HEIGHT, BOX_HEIGHT + (len(actions) - 1) * 16) if has_actions else BOX_HEIGHT

        # Draw box background
        box_id = self._canvas.create_rectangle(
            lx, ly, lx + BOX_WIDTH, ly + total_height,
            fill=fill, outline=BOX_OUTLINE, width=1,
        )

        # Draw axis indicator for stick inputs
        axis_tag = None
        if inp.name.endswith("_x"):
            axis_tag = "X"
        elif inp.name.endswith("_y"):
            axis_tag = "Y"

        items = [box_id]

        # Draw input label (small, at top of box)
        label = inp.display_name
        if axis_tag:
            label_color = AXIS_INDICATOR_COLORS[axis_tag]
        else:
            label_color = "#555555"

        label_id = self._canvas.create_text(
            lx + BOX_PAD, ly + 2,
            text=label, anchor=tk.NW,
            font=("Arial", 7), fill=label_color,
        )
        items.append(label_id)

        # Draw action names or unassigned text
        if has_actions:
            for i, action in enumerate(actions):
                txt_id = self._canvas.create_text(
                    lx + BOX_PAD, ly + 12 + i * 16,
                    text=action, anchor=tk.NW,
                    font=("Arial", 8, "bold"), fill=ASSIGNED_COLOR,
                )
                items.append(txt_id)
        else:
            txt_id = self._canvas.create_text(
                lx + BOX_PAD, ly + 12,
                text=UNASSIGNED_TEXT, anchor=tk.NW,
                font=("Arial", 8), fill=UNASSIGNED_COLOR,
            )
            items.append(txt_id)

        self._box_items[inp.name] = items

    def _hit_test(self, x: float, y: float) -> str | None:
        """Return the input name if (x, y) is inside a binding box."""
        for name, item_ids in self._box_items.items():
            if not item_ids:
                continue
            box_id = item_ids[0]  # First item is the rectangle
            coords = self._canvas.coords(box_id)
            if len(coords) == 4:
                x1, y1, x2, y2 = coords
                if x1 <= x <= x2 and y1 <= y <= y2:
                    return name
        return None

    def _on_mouse_move(self, event):
        """Highlight binding box on hover."""
        hit = self._hit_test(event.x, event.y)
        if hit != self._hover_input:
            # Unhighlight previous
            if self._hover_input and self._hover_input in self._box_items:
                items = self._box_items[self._hover_input]
                if items:
                    has_actions = bool(self._bindings.get(self._hover_input))
                    fill = BOX_FILL_ASSIGNED if has_actions else BOX_FILL
                    self._canvas.itemconfig(items[0], fill=fill)

            # Highlight current
            if hit and hit in self._box_items:
                items = self._box_items[hit]
                if items:
                    self._canvas.itemconfig(items[0], fill=BOX_FILL_HOVER)
                self._canvas.config(cursor="hand2")
            else:
                self._canvas.config(cursor="")

            self._hover_input = hit

    def _on_click(self, event):
        """Handle click on a binding box."""
        hit = self._hit_test(event.x, event.y)
        if hit and self._on_binding_click:
            self._on_binding_click(hit)
