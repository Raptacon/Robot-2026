"""Shared utilities for the dialog-based curve editors and widgets.

Contains constants, coordinate helpers, grid drawing, undo stack,
and math utilities shared across spline_editor, segment_editor,
curve_editor_widget, and preview_widget.
"""

import math
from copy import deepcopy

from host.controller_config.colors import (
    GRID_AXIS,
    GRID_MAJOR,
    GRID_MINOR,
    LABEL_COLOR,
)


# ---------------------------------------------------------------------------
#   Dialog canvas constants (spline_editor + segment_editor)
# ---------------------------------------------------------------------------

DIALOG_W = 600
DIALOG_H = 600
DIALOG_MARGIN = 50
DIALOG_PLOT_W = DIALOG_W - 2 * DIALOG_MARGIN
DIALOG_PLOT_H = DIALOG_H - 2 * DIALOG_MARGIN

# Border outline for editor canvases
_BORDER_OUTLINE = "#808080"


# ---------------------------------------------------------------------------
#   Grid drawing
# ---------------------------------------------------------------------------

def draw_editor_grid(canvas, d2c_fn, margin, plot_w, plot_h,
                     canvas_w, canvas_h,
                     x_min=-1.0, x_max=1.0,
                     y_min=-1.0, y_max=1.0):
    """Draw the grid with axis labels for a dialog editor.

    Args:
        canvas: tk.Canvas to draw on.
        d2c_fn: callable(x, y) -> (cx, cy) mapping data to canvas coords.
        margin: pixel margin around the plot area.
        plot_w: plot area width in pixels.
        plot_h: plot area height in pixels.
        canvas_w: total canvas width in pixels.
        canvas_h: total canvas height in pixels.
        x_min: minimum X data value (default -1.0).
        x_max: maximum X data value (default 1.0).
        y_min: minimum Y data value (default -1.0).
        y_max: maximum Y data value (default 1.0).
    """
    x_step = nice_grid_step(x_max - x_min)
    y_step = nice_grid_step(y_max - y_min)

    # Vertical grid lines (X axis)
    v = math.ceil(x_min / (x_step / 2)) * (x_step / 2)
    while v <= x_max + 1e-9:
        cx, _ = d2c_fn(v, 0)
        is_axis = abs(v) < 1e-9
        is_major = abs(round(v / x_step) * x_step - v) < 1e-9
        color = GRID_AXIS if is_axis else (GRID_MAJOR if is_major else GRID_MINOR)
        w = 2 if is_axis else 1
        canvas.create_line(cx, margin, cx, margin + plot_h,
                           fill=color, width=w)
        v += x_step / 2

    # Horizontal grid lines (Y axis)
    v = math.ceil(y_min / (y_step / 2)) * (y_step / 2)
    while v <= y_max + 1e-9:
        _, cy = d2c_fn(0, v)
        is_axis = abs(v) < 1e-9
        is_major = abs(round(v / y_step) * y_step - v) < 1e-9
        color = GRID_AXIS if is_axis else (GRID_MAJOR if is_major else GRID_MINOR)
        w = 2 if is_axis else 1
        canvas.create_line(margin, cy, margin + plot_w, cy,
                           fill=color, width=w)
        v += y_step / 2

    # X-axis labels (at major steps)
    v = math.ceil(x_min / x_step) * x_step
    while v <= x_max + 1e-9:
        cx, _ = d2c_fn(v, 0)
        canvas.create_text(cx, margin + plot_h + 15,
                           text=f"{v:g}", fill=LABEL_COLOR,
                           font=("TkDefaultFont", 8))
        v += x_step

    # Y-axis labels (at major steps)
    v = math.ceil(y_min / y_step) * y_step
    while v <= y_max + 1e-9:
        _, cy = d2c_fn(0, v)
        canvas.create_text(margin - 22, cy,
                           text=f"{v:g}", fill=LABEL_COLOR,
                           font=("TkDefaultFont", 8))
        v += y_step

    canvas.create_text(canvas_w / 2, canvas_h - 5,
                       text="Input", fill=LABEL_COLOR,
                       font=("TkDefaultFont", 9))
    canvas.create_text(12, canvas_h / 2, text="Output",
                       fill=LABEL_COLOR, font=("TkDefaultFont", 9), angle=90)
    canvas.create_rectangle(margin, margin,
                            margin + plot_w, margin + plot_h,
                            outline=_BORDER_OUTLINE)


# ---------------------------------------------------------------------------
#   Undo stack
# ---------------------------------------------------------------------------

class UndoStack:
    """Simple deepcopy-based undo stack with a fixed capacity."""

    def __init__(self, max_size=30):
        self._stack: list = []
        self._max = max_size

    def push(self, state):
        """Save a deepcopy of state onto the stack."""
        self._stack.append(deepcopy(state))
        if len(self._stack) > self._max:
            self._stack.pop(0)

    def pop(self):
        """Restore and return the most recent state, or None if empty."""
        if not self._stack:
            return None
        return self._stack.pop()

    def clear(self):
        """Remove all entries from the stack."""
        self._stack.clear()

    def __len__(self):
        return len(self._stack)


# ---------------------------------------------------------------------------
#   Grid step calculation
# ---------------------------------------------------------------------------

def nice_grid_step(span: float) -> float:
    """Choose a nice gridline step for the given data span.

    Aims for approximately 4 gridlines across the span.
    """
    if span <= 0:
        return 0.5
    raw = span / 4  # aim for ~4 gridlines
    mag = 10 ** math.floor(math.log10(raw))
    norm = raw / mag
    if norm < 1.5:
        return mag
    elif norm < 3.5:
        return 2 * mag
    elif norm < 7.5:
        return 5 * mag
    else:
        return 10 * mag
