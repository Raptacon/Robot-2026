"""Embeddable, resizable curve editor widget for the Action Editor tab.

Supports five modes:
  - "spline"   — interactive cubic hermite spline editing
  - "segment"  — interactive piecewise-linear editing
  - "raw"      — read-only visualization of y = x
  - "scaled"   — visualization with draggable scale handle
  - "squared"  — visualization with draggable scale handle (quadratic)
  - None       — inactive (button input type or no action selected)
"""

import math
import tkinter as tk
from copy import deepcopy
from tkinter import ttk, filedialog, messagebox

import yaml

from host.controller_config.colors import (
    BG_INACTIVE,
    BG_WHITE,
    CURVE_LINE,
    ENDPOINT_FILL,
    GRID_AXIS,
    GRID_MAJOR,
    GRID_MINOR,
    HANDLE_FILL,
    HANDLE_LINE,
    LABEL_COLOR,
    MIRROR_LINE,
    POINT_FILL,
    POINT_OUTLINE,
)
from utils.controller.model import (
    ActionDefinition,
    EventTriggerMode,
    EXTRA_SEGMENT_POINTS,
    EXTRA_SPLINE_POINTS,
    InputType,
)
from utils.math.curves import (
    evaluate_segments,
    evaluate_spline,
    default_spline_points,
    default_segment_points,
    numerical_slope,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_X_GAP = 0.04
_POINT_RADIUS = 7
_HANDLE_RADIUS = 5
_CURVE_SAMPLES_PER_SEG = 80
_VIS_SAMPLES = 200          # samples for visualization curves

# Colors (shared palette imported from colors.py)
_BG = BG_WHITE
_BG_INACTIVE = BG_INACTIVE
_GRID = GRID_MINOR
_GRID_MAJOR = GRID_MAJOR
_AXIS = GRID_AXIS
_CURVE = CURVE_LINE
_POINT_FILL = POINT_FILL
_POINT_OUTLINE = POINT_OUTLINE
_ENDPOINT_FILL = ENDPOINT_FILL
_HANDLE_FILL = HANDLE_FILL
_HANDLE_LINE = HANDLE_LINE
_LABEL = LABEL_COLOR
_DEADBAND_FILL = "#e0e0e0"
_SCALE_HANDLE = "#d08020"
_SCALE_HANDLE_OUTLINE = "#906010"
_MIRROR_FILL = MIRROR_LINE
_TRACKER_FILL = "#ff6600"
_TRACKER_RADIUS = 4
_TRACKER_TAG = "tracker"


# ---------------------------------------------------------------------------
# CurveEditorWidget
# ---------------------------------------------------------------------------

class CurveEditorWidget(ttk.Frame):
    """Embeddable curve editor supporting spline, segment, and visualization
    modes.

    Replaces the Phase 2 placeholder in the lower-left pane of the
    Action Editor tab.
    """

    def __init__(self, parent, *,
                 on_before_change=None,
                 on_curve_changed=None,
                 get_other_curves=None):
        super().__init__(parent)

        self._on_before_change = on_before_change
        self._on_curve_changed = on_curve_changed
        self._get_other_curves = get_other_curves

        self._action: ActionDefinition | None = None
        self._qname: str | None = None
        self._mode: str | None = None  # spline/segment/raw/scaled/squared
        self._points: list[dict] = []

        # Drag state
        self._drag_type = None   # "point", "handle", or "scale_handle"
        self._drag_idx = None
        self._drag_side = None   # "in" or "out" (spline handles)
        self._drag_undo_pushed = False

        # Options
        self._symmetric = False
        self._monotonic = True

        # Undo stack (max 30)
        self._undo_stack: list[list[dict]] = []

        # Canvas sizing (computed on configure)
        self._margin_x = 35
        self._margin_y = 35
        self._plot_w = 0
        self._plot_h = 0

        # X-axis range: -1..1 for sticks, 0..1 for triggers
        self._x_min = -1.0

        # Y-axis range: defaults to (-1, 1), auto-scaled for visualization
        self._y_min = -1.0
        self._y_max = 1.0

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Toolbar (top)
        self._toolbar = ttk.Frame(self)
        self._toolbar.pack(fill=tk.X, padx=2, pady=(2, 0))

        self._sym_var = tk.BooleanVar()
        self._sym_cb = ttk.Checkbutton(
            self._toolbar, text="Symmetry",
            variable=self._sym_var, command=self._on_symmetry_toggle)
        self._sym_cb.pack(side=tk.LEFT, padx=3)

        self._mono_var = tk.BooleanVar(value=True)
        self._mono_cb = ttk.Checkbutton(
            self._toolbar, text="Monotonic",
            variable=self._mono_var, command=self._on_monotonic_toggle)
        self._mono_cb.pack(side=tk.LEFT, padx=3)

        self._undo_btn = ttk.Button(
            self._toolbar, text="Undo", command=self._pop_undo, width=5)
        self._undo_btn.pack(side=tk.LEFT, padx=3)

        self._reset_btn = ttk.Button(
            self._toolbar, text="Reset", command=self._on_reset, width=5)
        self._reset_btn.pack(side=tk.LEFT, padx=3)

        self._export_btn = ttk.Button(
            self._toolbar, text="Export", command=self._on_export, width=6)
        self._export_btn.pack(side=tk.LEFT, padx=3)

        self._import_btn = ttk.Button(
            self._toolbar, text="Import", command=self._on_import, width=6)
        self._import_btn.pack(side=tk.LEFT, padx=3)

        self._copy_btn = ttk.Button(
            self._toolbar, text="Copy from...",
            command=self._on_copy_from, width=10)
        self._copy_btn.pack(side=tk.LEFT, padx=3)

        # Visualization toolbar (shown for scaled/squared modes)
        self._vis_toolbar = ttk.Frame(self)
        self._wide_range_var = tk.BooleanVar(value=False)
        self._wide_range_cb = ttk.Checkbutton(
            self._vis_toolbar, text="Wide range",
            variable=self._wide_range_var,
            command=self._on_wide_range_toggle)
        self._wide_range_cb.pack(side=tk.LEFT, padx=3)

        # Canvas (fills remaining space)
        self._canvas = tk.Canvas(self, bg=_BG_INACTIVE,
                                 highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", self._on_right_click)
        self._canvas.bind("<Motion>", self._on_mouse_move)
        self._canvas.bind("<Leave>", self._on_mouse_leave)

        # Status bar (bottom)
        self._status_var = tk.StringVar(value="No action selected")
        ttk.Label(self, textvariable=self._status_var,
                  relief=tk.SUNKEN, anchor=tk.W,
                  font=("TkDefaultFont", 7)).pack(
                      fill=tk.X, padx=2, pady=(0, 2))

        self.bind("<Control-z>", self._on_ctrl_z)

        # Start with toolbar hidden
        self._toolbar.pack_forget()

    # ------------------------------------------------------------------
    # Dynamic Canvas Sizing
    # ------------------------------------------------------------------

    def _on_canvas_configure(self, event):
        w, h = event.width, event.height
        if w < 20 or h < 20:
            return

        margin_x = max(25, min(50, int(w * 0.08)))
        margin_y = max(25, min(50, int(h * 0.08)))

        available_w = w - 2 * margin_x
        available_h = h - 2 * margin_y

        # Square plot area
        plot_size = max(10, min(available_w, available_h))

        self._margin_x = margin_x + (available_w - plot_size) // 2
        self._margin_y = margin_y + (available_h - plot_size) // 2
        self._plot_w = plot_size
        self._plot_h = plot_size

        self._draw()

    # ------------------------------------------------------------------
    # Coordinate Conversion
    # ------------------------------------------------------------------

    def _d2c(self, x: float, y: float) -> tuple[float, float]:
        """Data coords to canvas pixels. X uses _x_min..1, Y uses _y_min/_y_max."""
        x_range = 1.0 - self._x_min
        if x_range == 0:
            x_range = 2.0
        cx = self._margin_x + (x - self._x_min) / x_range * self._plot_w
        y_range = self._y_max - self._y_min
        if y_range == 0:
            y_range = 2.0
        cy = self._margin_y + (self._y_max - y) / y_range * self._plot_h
        return cx, cy

    def _c2d(self, cx: float, cy: float) -> tuple[float, float]:
        """Canvas pixels to data coords."""
        if self._plot_w == 0 or self._plot_h == 0:
            return 0.0, 0.0
        x_range = 1.0 - self._x_min
        if x_range == 0:
            x_range = 2.0
        x = (cx - self._margin_x) / self._plot_w * x_range + self._x_min
        y_range = self._y_max - self._y_min
        if y_range == 0:
            y_range = 2.0
        y = self._y_max - (cy - self._margin_y) / self._plot_h * y_range
        return x, y

    @property
    def _display_scale(self) -> float:
        """Scale factor applied to displayed Y values in editable modes.

        Includes inversion as a sign flip so the curve visually reflects
        the runtime shaping pipeline.  This is exact for odd-symmetric
        curves (the common case) and a close approximation otherwise.
        """
        if self._action and self._mode in ("spline", "segment"):
            s = self._action.scale
            if self._action.inversion:
                s = -s
            return s
        return 1.0

    @property
    def _handle_length(self) -> float:
        return max(20, self._plot_w * 0.1)

    def _tangent_offset(self, tangent: float) -> tuple[float, float]:
        """Tangent slope to canvas-pixel offset for handle drawing.

        Accounts for display scale and dynamic Y range so handles
        visually match the scaled curve direction.
        """
        # Pixels per data unit in each axis
        x_range = 1.0 - self._x_min
        if x_range == 0:
            x_range = 2.0
        ppx = self._plot_w / x_range
        y_range = self._y_max - self._y_min
        if y_range == 0:
            y_range = 2.0
        ppy = self._plot_h / y_range
        if ppx < 1 or ppy < 1:
            return self._handle_length, 0.0
        # Tangent is raw dy/dx; scale it for display
        vis_tangent = tangent * self._display_scale
        dx = 1.0 * ppx
        dy = -vis_tangent * ppy
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return self._handle_length, 0.0
        s = self._handle_length / length
        return dx * s, dy * s

    def _offset_to_tangent(self, dx: float, dy: float) -> float:
        """Canvas-pixel offset back to raw tangent slope (un-scaled)."""
        x_range = 1.0 - self._x_min
        if x_range == 0:
            x_range = 2.0
        ppx = self._plot_w / x_range
        y_range = self._y_max - self._y_min
        if y_range == 0:
            y_range = 2.0
        ppy = self._plot_h / y_range
        if ppx < 1 or ppy < 1:
            return 1.0
        data_dx = dx / ppx
        data_dy = -dy / ppy
        if abs(data_dx) < 1e-6:
            return 10.0 if data_dy > 0 else -10.0
        vis_tangent = data_dy / data_dx
        # Un-scale to get raw tangent
        s = self._display_scale
        if abs(s) < 1e-6:
            return vis_tangent
        return vis_tangent / s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Input names that only produce 0..1 (Xbox triggers)
    _TRIGGER_INPUTS = {"left_trigger", "right_trigger"}

    def load_action(self, action: ActionDefinition, qname: str,
                    bound_inputs: list[str] | None = None):
        """Populate the widget from the given action.

        Args:
            bound_inputs: list of input names bound to this action.
                If all are trigger inputs (0..1 range), the X axis
                adjusts from -1..1 to 0..1.
        """
        self._update_x_range(bound_inputs)
        self._action = action
        self._qname = qname
        self._undo_stack.clear()
        self._drag_type = None
        self._symmetric = False
        self._sym_var.set(False)
        self._monotonic = True
        self._mono_var.set(True)

        # Determine mode from input_type + trigger_mode
        if action.input_type != InputType.ANALOG:
            self._mode = None
        elif action.trigger_mode == EventTriggerMode.SPLINE:
            self._mode = "spline"
        elif action.trigger_mode == EventTriggerMode.SEGMENTED:
            self._mode = "segment"
        elif action.trigger_mode == EventTriggerMode.RAW:
            self._mode = "raw"
        elif action.trigger_mode == EventTriggerMode.SCALED:
            self._mode = "scaled"
        elif action.trigger_mode == EventTriggerMode.SQUARED:
            self._mode = "squared"
        else:
            self._mode = None

        # Load points for editable modes
        if self._mode == "spline":
            pts = action.extra.get(EXTRA_SPLINE_POINTS)
            if not pts:
                pts = default_spline_points()
                action.extra[EXTRA_SPLINE_POINTS] = pts
            self._points = [dict(p) for p in pts]
            self._points.sort(key=lambda p: p["x"])
        elif self._mode == "segment":
            pts = action.extra.get(EXTRA_SEGMENT_POINTS)
            if not pts:
                pts = default_segment_points()
                action.extra[EXTRA_SEGMENT_POINTS] = pts
            self._points = [{"x": p["x"], "y": p["y"]} for p in pts]
            self._points.sort(key=lambda p: p["x"])
        else:
            self._points = []

        self._update_toolbar()
        self._update_canvas_bg()
        self._draw()

    def clear(self):
        """Clear to inactive state."""
        self._action = None
        self._qname = None
        self._mode = None
        self._points = []
        self._undo_stack.clear()
        self._drag_type = None
        self._update_toolbar()
        self._update_canvas_bg()
        self._draw()

    def get_mode(self) -> str | None:
        return self._mode

    def refresh(self):
        """Redraw from current action (call after external parameter change)."""
        if self._action:
            # Re-determine mode in case trigger_mode changed
            old_mode = self._mode
            self.load_action(self._action, self._qname)
            # Don't reset undo if mode didn't change
            if old_mode == self._mode:
                pass  # undo already cleared by load_action; acceptable
        else:
            self._draw()

    def update_bindings(self, bound_inputs: list[str] | None = None):
        """Update X range when bindings change (assign/unassign)."""
        old_x_min = self._x_min
        self._update_x_range(bound_inputs)
        if self._x_min != old_x_min:
            self._draw()

    def _update_x_range(self, bound_inputs: list[str] | None):
        """Set X range based on bound input types.

        If ALL bound inputs are triggers (0..1), use 0..1.
        Otherwise use -1..1 (sticks, or no bindings).
        None means 'keep current' (e.g. refresh without rebinding).
        """
        if bound_inputs is None:
            return
        if bound_inputs and all(
                inp in self._TRIGGER_INPUTS for inp in bound_inputs):
            self._x_min = 0.0
        else:
            self._x_min = -1.0

    # ------------------------------------------------------------------
    # Toolbar Management
    # ------------------------------------------------------------------

    def _update_toolbar(self):
        """Show/hide toolbar and mode-specific controls."""
        is_editable = self._mode in ("spline", "segment")
        is_vis_draggable = self._mode in ("scaled", "squared")
        if is_editable:
            self._vis_toolbar.pack_forget()
            self._toolbar.pack(fill=tk.X, padx=2, pady=(2, 0))
            # Repack canvas after toolbar
            self._canvas.pack_forget()
            self._canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            # Show/hide monotonic
            if self._mode == "segment":
                self._mono_cb.pack(side=tk.LEFT, padx=3,
                                   after=self._sym_cb)
            else:
                self._mono_cb.pack_forget()
        elif is_vis_draggable:
            self._toolbar.pack_forget()
            self._vis_toolbar.pack(fill=tk.X, padx=2, pady=(2, 0))
            # Repack canvas after vis toolbar
            self._canvas.pack_forget()
            self._canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        else:
            self._toolbar.pack_forget()
            self._vis_toolbar.pack_forget()

    def _update_canvas_bg(self):
        bg = _BG_INACTIVE if self._mode is None else _BG
        self._canvas.configure(bg=bg)
        cursor = "crosshair" if self._mode in ("spline", "segment") else ""
        self._canvas.configure(cursor=cursor)
        if self._mode is None:
            self._status_var.set("No action selected")
        elif self._mode == "raw":
            self._status_var.set("Read-only: raw input (no shaping)")
        elif self._mode in ("scaled", "squared"):
            self._status_var.set("Drag handle to adjust scale")
        elif self._mode == "spline":
            self._status_var.set(
                "Click to add | Right-click to remove | Drag to adjust")
        elif self._mode == "segment":
            self._status_var.set(
                "Click to add | Right-click to remove | Drag to adjust")

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _compute_y_range(self):
        """Compute Y-axis range, auto-scaling when curve extends beyond -1..1."""
        if (self._mode in ("raw", "scaled", "squared")
                and self._action and self._wide_range_var.get()):
            y_min = 0.0
            y_max = 0.0
            x_span = 1.0 - self._x_min
            for i in range(_VIS_SAMPLES + 1):
                x = self._x_min + x_span * i / _VIS_SAMPLES
                y = self._compute_shaped_value(x)
                y_min = min(y_min, y)
                y_max = max(y_max, y)
            # Ensure range includes at least -1..1
            y_min = min(y_min, -1.0)
            y_max = max(y_max, 1.0)
            pad = (y_max - y_min) * 0.05
            self._y_min = y_min - pad
            self._y_max = y_max + pad
        elif self._mode in ("spline", "segment") and self._action:
            s = abs(self._display_scale)
            # Find actual curve extent (spline can overshoot control points)
            if s > 1e-6 and self._points and len(self._points) >= 2:
                y_min = 0.0
                y_max = 0.0
                for pt in self._points:
                    y_min = min(y_min, pt["y"] * self._display_scale)
                    y_max = max(y_max, pt["y"] * self._display_scale)
                if self._mode == "spline":
                    pts = self._points
                    n = 20 * (len(pts) - 1)
                    x_lo, x_hi = pts[0]["x"], pts[-1]["x"]
                    for i in range(n + 1):
                        x = x_lo + (x_hi - x_lo) * i / n
                        y = evaluate_spline(pts, x) * self._display_scale
                        y_min = min(y_min, y)
                        y_max = max(y_max, y)
                y_min = min(y_min, -1.0)
                y_max = max(y_max, 1.0)
                pad = (y_max - y_min) * 0.05
                self._y_min = y_min - pad
                self._y_max = y_max + pad
            else:
                self._y_min = -1.0
                self._y_max = 1.0
        else:
            self._y_min = -1.0
            self._y_max = 1.0

    def _draw(self):
        c = self._canvas
        c.delete("all")

        if self._plot_w < 10 or self._plot_h < 10:
            return

        if self._mode is None:
            self._draw_inactive()
            return

        self._compute_y_range()
        self._draw_grid()

        if self._mode in ("raw", "scaled", "squared"):
            self._draw_deadband_band()
            self._draw_computed_curve()
            if self._mode in ("scaled", "squared"):
                self._draw_scale_handle()
        elif self._mode == "spline":
            self._draw_spline_curve()
            self._draw_handles()
            self._draw_points()
        elif self._mode == "segment":
            self._draw_segment_curve()
            self._draw_points()

    def _draw_inactive(self):
        c = self._canvas
        cw = int(c.cget("width")) if c.winfo_width() < 2 else c.winfo_width()
        ch = int(c.cget("height")) if c.winfo_height() < 2 else c.winfo_height()
        c.create_text(cw // 2, ch // 2,
                      text="Select an analog action to view curve",
                      fill="#999999", font=("TkDefaultFont", 10))

    def _nice_grid_step(self, span: float) -> float:
        """Choose a nice gridline step for the given data span."""
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

    def _draw_grid(self):
        c = self._canvas
        small = self._plot_w < 200

        # X gridlines (dynamic based on x_min)
        if self._x_min >= 0:
            x_grid = [i / 4 for i in range(0, 5)]  # 0, 0.25, 0.5, 0.75, 1
        else:
            x_grid = [i / 4 for i in range(-4, 5)]  # -1..1 by 0.25
        for v in x_grid:
            cx, _ = self._d2c(v, 0)
            is_axis = abs(v) < 0.01
            is_major = abs(v * 2) % 1 < 0.01
            if small and not is_axis and not is_major:
                continue
            color = _AXIS if is_axis else (_GRID_MAJOR if is_major else _GRID)
            w = 2 if is_axis else 1
            c.create_line(cx, self._margin_y,
                          cx, self._margin_y + self._plot_h,
                          fill=color, width=w)

        # Y gridlines (dynamic range)
        y_step = self._nice_grid_step(self._y_max - self._y_min)
        # Start from a rounded value below y_min
        y_start = math.floor(self._y_min / y_step) * y_step
        v = y_start
        while v <= self._y_max + y_step * 0.01:
            _, cy = self._d2c(0, v)
            is_axis = abs(v) < y_step * 0.01
            color = _AXIS if is_axis else _GRID_MAJOR
            w = 2 if is_axis else 1
            c.create_line(self._margin_x, cy,
                          self._margin_x + self._plot_w, cy,
                          fill=color, width=w)
            v += y_step

        # Labels
        if self._plot_w >= 100:
            font_size = 7 if self._plot_w < 250 else 8
            # X labels
            if self._x_min >= 0:
                x_labels = [0.0, 0.25, 0.5, 0.75, 1.0]
            else:
                x_labels = [-1.0, -0.5, 0.0, 0.5, 1.0]
            for v in x_labels:
                cx, _ = self._d2c(v, 0)
                c.create_text(cx, self._margin_y + self._plot_h + 12,
                              text=f"{v:g}", fill=_LABEL,
                              font=("TkDefaultFont", font_size))
            # Y labels
            v = y_start
            while v <= self._y_max + y_step * 0.01:
                _, cy = self._d2c(0, v)
                c.create_text(self._margin_x - 18, cy,
                              text=f"{v:g}", fill=_LABEL,
                              font=("TkDefaultFont", font_size))
                v += y_step

        # Reference lines at ±1 when Y range extends beyond -1..1
        if self._y_min < -1.05 or self._y_max > 1.05:
            for ref_y in (-1.0, 1.0):
                _, ry = self._d2c(0, ref_y)
                c.create_line(self._margin_x, ry,
                              self._margin_x + self._plot_w, ry,
                              fill="#b0b0ff", width=1, dash=(6, 3))

        # Border
        c.create_rectangle(self._margin_x, self._margin_y,
                           self._margin_x + self._plot_w,
                           self._margin_y + self._plot_h,
                           outline="#808080")

    # --- Visualization Modes ---

    def _compute_shaped_value(self, x: float) -> float:
        """Compute the shaped output for visualization modes."""
        if not self._action:
            return x

        # RAW bypasses all shaping
        if self._mode == "raw":
            return x

        val = x

        # 1. Inversion
        if self._action.inversion:
            val = -val

        # 2. Deadband
        db = self._action.deadband
        if db > 0 and abs(val) < db:
            val = 0.0
        elif db > 0:
            sign = 1.0 if val >= 0 else -1.0
            val = sign * (abs(val) - db) / (1.0 - db) if db < 1.0 else 0.0

        # 3. Curve function
        if self._mode == "squared":
            sign = 1.0 if val >= 0 else -1.0
            val = sign * val * val

        # 4. Scale
        val = val * self._action.scale

        return val

    def _draw_computed_curve(self):
        """Draw the visualization curve for raw/scaled/squared modes."""
        c = self._canvas
        coords = []
        x_span = 1.0 - self._x_min
        for i in range(_VIS_SAMPLES + 1):
            x = self._x_min + x_span * i / _VIS_SAMPLES
            y = self._compute_shaped_value(x)
            cx, cy = self._d2c(x, y)
            coords.extend([cx, cy])
        if len(coords) >= 4:
            c.create_line(*coords, fill=_CURVE, width=2, smooth=False)

    def _draw_deadband_band(self):
        """Draw shaded deadband region."""
        if not self._action or self._action.deadband <= 0:
            return
        db = self._action.deadband
        x0, y0 = self._d2c(-db, self._y_max)
        x1, y1 = self._d2c(db, self._y_min)
        self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill=_DEADBAND_FILL, outline="", stipple="gray25")

    def _draw_scale_handle(self):
        """Draw draggable scale handle at (1.0, f(1.0))."""
        if not self._action:
            return
        y_val = self._compute_shaped_value(1.0)
        cx, cy = self._d2c(1.0, y_val)
        r = _POINT_RADIUS + 1
        # Diamond shape
        self._canvas.create_polygon(
            cx, cy - r, cx + r, cy, cx, cy + r, cx - r, cy,
            fill=_SCALE_HANDLE, outline=_SCALE_HANDLE_OUTLINE, width=2)

    # --- Spline Mode ---

    def _draw_spline_curve(self):
        pts = self._points
        if len(pts) < 2:
            return
        s = self._display_scale
        n = _CURVE_SAMPLES_PER_SEG * (len(pts) - 1)
        x_min, x_max = pts[0]["x"], pts[-1]["x"]
        coords = []
        for i in range(n + 1):
            x = x_min + (x_max - x_min) * i / n
            y = evaluate_spline(pts, x) * s
            cx, cy = self._d2c(x, y)
            coords.extend([cx, cy])
        if len(coords) >= 4:
            self._canvas.create_line(
                *coords, fill=_CURVE, width=2, smooth=False)

    def _draw_handles(self):
        c = self._canvas
        s = self._display_scale
        for i, pt in enumerate(self._points):
            cx, cy = self._d2c(pt["x"], pt["y"] * s)
            hdx, hdy = self._tangent_offset(pt["tangent"])
            c.create_line(cx - hdx, cy - hdy, cx + hdx, cy + hdy,
                          fill=_HANDLE_LINE, width=1, dash=(4, 4))
            if i > 0:
                hx, hy = cx - hdx, cy - hdy
                c.create_oval(hx - _HANDLE_RADIUS, hy - _HANDLE_RADIUS,
                              hx + _HANDLE_RADIUS, hy + _HANDLE_RADIUS,
                              fill=_HANDLE_FILL, outline="#308030")
            if i < len(self._points) - 1:
                hx, hy = cx + hdx, cy + hdy
                c.create_oval(hx - _HANDLE_RADIUS, hy - _HANDLE_RADIUS,
                              hx + _HANDLE_RADIUS, hy + _HANDLE_RADIUS,
                              fill=_HANDLE_FILL, outline="#308030")

    # --- Segment Mode ---

    def _draw_segment_curve(self):
        pts = self._points
        if len(pts) < 2:
            return
        s = self._display_scale
        coords = []
        for pt in pts:
            cx, cy = self._d2c(pt["x"], pt["y"] * s)
            coords.extend([cx, cy])
        if len(coords) >= 4:
            self._canvas.create_line(
                *coords, fill=_CURVE, width=2, smooth=False)

    # --- Points (shared by editable modes) ---

    def _draw_points(self):
        c = self._canvas
        s = self._display_scale
        for i, pt in enumerate(self._points):
            cx, cy = self._d2c(pt["x"], pt["y"] * s)
            is_endpoint = (i == 0 or i == len(self._points) - 1)
            is_mirror = (self._symmetric
                         and pt["x"] < -_MIN_X_GAP / 2)
            if is_mirror:
                fill = _MIRROR_FILL
            elif is_endpoint:
                fill = _ENDPOINT_FILL
            else:
                fill = _POINT_FILL
            c.create_oval(cx - _POINT_RADIUS, cy - _POINT_RADIUS,
                          cx + _POINT_RADIUS, cy + _POINT_RADIUS,
                          fill=fill, outline=_POINT_OUTLINE, width=2)

    # ------------------------------------------------------------------
    # Curve Tracker (follow mouse along curve)
    # ------------------------------------------------------------------

    def _evaluate_display_y(self, x: float) -> float | None:
        """Return the displayed Y value on the curve at data-x, or None."""
        if self._mode in ("raw", "scaled", "squared"):
            return self._compute_shaped_value(x)
        elif self._mode == "spline" and len(self._points) >= 2:
            return evaluate_spline(self._points, x) * self._display_scale
        elif self._mode == "segment" and len(self._points) >= 2:
            return evaluate_segments(self._points, x) * self._display_scale
        return None

    def _on_mouse_move(self, event):
        """Draw a tracking dot that follows the curve under the cursor."""
        self._canvas.delete(_TRACKER_TAG)
        if self._mode is None or self._drag_type is not None:
            return
        x, _ = self._c2d(event.x, event.y)
        if x < self._x_min or x > 1.0:
            return
        y = self._evaluate_display_y(x)
        if y is None:
            return
        cx, cy = self._d2c(x, y)
        r = _TRACKER_RADIUS
        self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=_TRACKER_FILL, outline="", tags=_TRACKER_TAG)
        # Label with X,Y offset to upper-right; flip if near edge
        label = f"({x:.2f}, {y:.2f})"
        lx = cx + 10 if cx < self._margin_x + self._plot_w - 80 else cx - 10
        ly = cy - 14 if cy > self._margin_y + 14 else cy + 14
        anchor = tk.SW if lx > cx else tk.SE
        if ly > cy:
            anchor = tk.NW if lx > cx else tk.NE
        self._canvas.create_text(
            lx, ly, text=label, fill=_TRACKER_FILL,
            font=("TkDefaultFont", 7), anchor=anchor,
            tags=_TRACKER_TAG)

    def _on_mouse_leave(self, event):
        """Remove tracker when mouse leaves the canvas."""
        self._canvas.delete(_TRACKER_TAG)

    # ------------------------------------------------------------------
    # Hit Testing
    # ------------------------------------------------------------------

    def _hit_test(self, cx, cy):
        """Find element at canvas position.

        Returns (type, idx, side) or None.
        """
        s = self._display_scale
        if self._mode == "spline":
            # Check handles first
            for i, pt in enumerate(self._points):
                if self._symmetric and pt["x"] < -_MIN_X_GAP / 2:
                    continue
                px, py = self._d2c(pt["x"], pt["y"] * s)
                hdx, hdy = self._tangent_offset(pt["tangent"])
                if i < len(self._points) - 1:
                    if math.hypot(cx - (px + hdx),
                                  cy - (py + hdy)) <= _HANDLE_RADIUS + 3:
                        return ("handle", i, "out")
                if i > 0:
                    if math.hypot(cx - (px - hdx),
                                  cy - (py - hdy)) <= _HANDLE_RADIUS + 3:
                        return ("handle", i, "in")

        if self._mode in ("spline", "segment"):
            for i, pt in enumerate(self._points):
                if self._symmetric and pt["x"] < -_MIN_X_GAP / 2:
                    continue
                px, py = self._d2c(pt["x"], pt["y"] * s)
                if math.hypot(cx - px, cy - py) <= _POINT_RADIUS + 3:
                    return ("point", i, None)

        if self._mode in ("scaled", "squared"):
            # Check scale handle
            y_val = self._compute_shaped_value(1.0)
            hcx, hcy = self._d2c(1.0, y_val)
            if math.hypot(cx - hcx, cy - hcy) <= _POINT_RADIUS + 5:
                return ("scale_handle", 0, None)

        return None

    # ------------------------------------------------------------------
    # Mouse Interaction
    # ------------------------------------------------------------------

    def _on_press(self, event):
        if self._mode is None:
            return

        hit = self._hit_test(event.x, event.y)
        if hit:
            self._drag_type, self._drag_idx, self._drag_side = hit
            self._drag_undo_pushed = False
        else:
            self._drag_type = None
            if self._mode in ("spline", "segment"):
                self._add_point_at(event.x, event.y)

    def _on_drag(self, event):
        if self._drag_type is None:
            return

        if self._drag_type == "scale_handle":
            self._drag_scale_handle(event)
            return

        if self._mode not in ("spline", "segment"):
            return

        if not self._drag_undo_pushed:
            self._push_undo()
            self._drag_undo_pushed = True

        i = self._drag_idx
        pt = self._points[i]

        s = self._display_scale

        if self._drag_type == "point":
            _, vis_y = self._c2d(event.x, event.y)
            # Un-scale cursor Y to get raw point Y
            y = vis_y / s if abs(s) > 1e-6 else vis_y
            is_endpoint = (i == 0 or i == len(self._points) - 1)

            # Center point with symmetry: y locked to 0
            if self._symmetric and abs(pt["x"]) < _MIN_X_GAP / 2:
                pt["y"] = 0.0
            else:
                y = max(-1.0, min(1.0, y))
                if self._mode == "segment" and self._monotonic:
                    y = self._clamp_monotonic(i, y)
                pt["y"] = round(y, 3)

            # Intermediate points: also move X
            if not is_endpoint:
                x, _ = self._c2d(event.x, event.y)
                x_lo = self._points[i - 1]["x"] + _MIN_X_GAP
                x_hi = self._points[i + 1]["x"] - _MIN_X_GAP
                if self._symmetric and pt["x"] > 0:
                    x_lo = max(x_lo, _MIN_X_GAP)
                pt["x"] = round(max(x_lo, min(x_hi, x)), 3)

                if self._mode == "segment" and self._monotonic:
                    pt["y"] = round(
                        self._clamp_monotonic(i, pt["y"]), 3)

        elif self._drag_type == "handle" and self._mode == "spline":
            cx, cy = self._d2c(pt["x"], pt["y"] * s)
            dx, dy = event.x - cx, event.y - cy
            if self._drag_side == "in":
                dx, dy = -dx, -dy
            if math.hypot(dx, dy) > 5:
                t = self._offset_to_tangent(dx, dy)
                pt["tangent"] = round(max(-10.0, min(10.0, t)), 3)

        if self._symmetric:
            self._enforce_symmetry()
            for j, p in enumerate(self._points):
                if p is pt:
                    self._drag_idx = j
                    break

        info = f"x={pt['x']:.2f}  y={pt['y']:.3f}"
        if self._mode == "spline":
            info += f"  tangent={pt.get('tangent', 0):.3f}"
        self._status_var.set(f"Point {self._drag_idx}: {info}")
        self._draw()

    def _drag_scale_handle(self, event):
        """Drag the scale handle to adjust action.scale.

        Uses pixel-delta from drag start for consistent sensitivity
        regardless of current Y range or scale magnitude.
        """
        if not self._action:
            return
        if not self._drag_undo_pushed:
            if self._on_before_change:
                self._on_before_change(200)
            self._drag_undo_pushed = True
            self._drag_start_y = event.y
            self._drag_start_scale = self._action.scale

        if self._plot_h <= 0:
            return

        # Compute unscaled base output at x=1.0
        old_scale = self._action.scale
        self._action.scale = 1.0
        base = self._compute_shaped_value(1.0)
        self._action.scale = old_scale

        # Pixel delta (positive = dragged up = increase if base > 0)
        delta_px = self._drag_start_y - event.y
        # Fixed rate: one full plot height = 2.0 scale units
        scale_per_px = 2.0 / self._plot_h
        # Match drag direction to curve direction
        direction = 1.0 if base >= 0 else -1.0
        new_scale = self._drag_start_scale + delta_px * scale_per_px * direction

        # Clamp scale: tighter when wide range is off
        if self._wide_range_var.get():
            new_scale = max(-10.0, min(10.0, new_scale))
        else:
            # Clamp so max output stays in [-1, 1]
            if abs(base) > 0.01:
                max_scale = 1.0 / abs(base)
                new_scale = max(-max_scale, min(max_scale, new_scale))
            else:
                new_scale = max(-1.0, min(1.0, new_scale))

        new_scale = round(new_scale, 2)
        self._action.scale = new_scale
        self._status_var.set(f"Scale: {new_scale:.2f}")
        self._draw()

        if self._on_curve_changed:
            self._on_curve_changed()

    def _on_release(self, event):
        if self._drag_type in ("point", "handle") and self._drag_undo_pushed:
            self._save_to_action()
        self._drag_type = None
        if self._mode in ("spline", "segment"):
            self._status_var.set(
                "Click to add | Right-click to remove | Drag to adjust")
        elif self._mode in ("scaled", "squared"):
            self._status_var.set("Drag handle to adjust scale")
        elif self._mode == "raw":
            self._status_var.set("Read-only: raw input (no shaping)")

    def _on_right_click(self, event):
        if self._mode not in ("spline", "segment"):
            return
        hit = self._hit_test(event.x, event.y)
        if not hit or hit[0] != "point":
            return
        i = hit[1]
        if i == 0 or i == len(self._points) - 1:
            self._status_var.set("Cannot remove endpoints")
            return
        if len(self._points) <= 2:
            self._status_var.set("Need at least 2 points")
            return
        self._drag_type = None
        self._remove_point(i)

    # ------------------------------------------------------------------
    # Point Add / Remove
    # ------------------------------------------------------------------

    def _add_point_at(self, cx, cy):
        x, vis_y = self._c2d(cx, cy)
        s = self._display_scale
        # Un-scale cursor Y to get raw point Y
        y = vis_y / s if abs(s) > 1e-6 else vis_y

        if self._symmetric and x < -_MIN_X_GAP / 2:
            self._status_var.set(
                "Add points on the positive side (symmetry)")
            return

        x_min = self._points[0]["x"]
        x_max = self._points[-1]["x"]
        if x <= x_min + _MIN_X_GAP or x >= x_max - _MIN_X_GAP:
            return
        y = max(-1.0, min(1.0, y))

        for pt in self._points:
            if abs(pt["x"] - x) < _MIN_X_GAP:
                return

        if self._mode == "segment" and self._monotonic:
            y = self._clamp_monotonic_insert(x, y)

        self._push_undo()
        new_pt = {"x": round(x, 3), "y": round(y, 3)}
        if self._mode == "spline":
            new_pt["tangent"] = round(numerical_slope(self._points, x), 3)
        self._points.append(new_pt)
        self._points.sort(key=lambda p: p["x"])

        if self._symmetric:
            self._enforce_symmetry()

        self._save_to_action()
        self._draw()
        self._status_var.set(
            f"Added point at x={x:.2f} ({len(self._points)} points)")

    def _remove_point(self, idx):
        if idx == 0 or idx == len(self._points) - 1:
            return
        if len(self._points) <= 2:
            return
        self._push_undo()
        self._points.pop(idx)
        if self._symmetric:
            self._enforce_symmetry()
        self._save_to_action()
        self._draw()
        self._status_var.set(
            f"Removed point ({len(self._points)} points)")

    # ------------------------------------------------------------------
    # Monotonic Constraint (segment mode)
    # ------------------------------------------------------------------

    def _clamp_monotonic(self, idx: int, y: float) -> float:
        if idx > 0:
            y = max(y, self._points[idx - 1]["y"])
        if idx < len(self._points) - 1:
            y = min(y, self._points[idx + 1]["y"])
        return y

    def _clamp_monotonic_insert(self, x: float, y: float) -> float:
        lo_y = -1.0
        hi_y = 1.0
        for pt in self._points:
            if pt["x"] < x:
                lo_y = max(lo_y, pt["y"])
            elif pt["x"] > x:
                hi_y = min(hi_y, pt["y"])
                break
        return max(lo_y, min(hi_y, y))

    def _enforce_monotonic(self):
        for i in range(1, len(self._points)):
            if self._points[i]["y"] < self._points[i - 1]["y"]:
                self._points[i]["y"] = self._points[i - 1]["y"]

    # ------------------------------------------------------------------
    # Symmetry
    # ------------------------------------------------------------------

    def _on_wide_range_toggle(self):
        """Toggle wide range mode for scaled/squared visualization."""
        self._draw()

    def _on_symmetry_toggle(self):
        self._push_undo()
        self._symmetric = self._sym_var.get()
        if self._symmetric:
            self._enforce_symmetry()
            self._save_to_action()
            self._draw()
            self._status_var.set("Symmetry on — edit positive side")

    def _enforce_symmetry(self):
        positive = [pt for pt in self._points
                    if pt["x"] > _MIN_X_GAP / 2]
        center = None
        for pt in self._points:
            if abs(pt["x"]) < _MIN_X_GAP / 2:
                center = pt
                break

        is_spline = self._mode == "spline"
        if center is None:
            center = {"x": 0.0, "y": 0.0}
            if is_spline:
                center["tangent"] = 1.0
        else:
            center["x"] = 0.0
            center["y"] = 0.0

        new_points = []
        for pt in reversed(positive):
            mirror = {"x": round(-pt["x"], 3), "y": round(-pt["y"], 3)}
            if is_spline:
                mirror["tangent"] = pt["tangent"]
            new_points.append(mirror)
        new_points.append(center)
        new_points.extend(positive)
        self._points = new_points

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def _push_undo(self):
        self._undo_stack.append(deepcopy(self._points))
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)

    def _on_ctrl_z(self, event):
        """Handle Ctrl+Z within the curve editor."""
        self._pop_undo()
        return "break"  # Prevent app-level bind_all undo from firing

    def _pop_undo(self):
        if not self._undo_stack:
            self._status_var.set("Nothing to undo")
            return
        self._points = self._undo_stack.pop()
        self._save_to_action(push_app_undo=False)
        self._draw()
        self._status_var.set(f"Undo ({len(self._undo_stack)} remaining)")

    # ------------------------------------------------------------------
    # Data Sync
    # ------------------------------------------------------------------

    def _save_to_action(self, push_app_undo=True):
        """Write points back to the action and notify.

        Args:
            push_app_undo: if True, push an undo snapshot to the app
                before saving. Set to False when called from _pop_undo
                so the curve editor's undo doesn't create a new app-level
                undo entry.
        """
        if not self._action:
            return
        if push_app_undo and self._on_before_change:
            self._on_before_change(200)
        if self._mode == "spline":
            self._action.extra[EXTRA_SPLINE_POINTS] = deepcopy(self._points)
        elif self._mode == "segment":
            self._action.extra[EXTRA_SEGMENT_POINTS] = deepcopy(self._points)
        if self._on_curve_changed:
            self._on_curve_changed()

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def _on_reset(self):
        if self._mode not in ("spline", "segment"):
            return
        self._push_undo()
        if self._mode == "spline":
            self._points = default_spline_points()
        else:
            self._points = default_segment_points()
        if self._symmetric:
            self._enforce_symmetry()
        if self._mode == "segment" and self._monotonic:
            self._enforce_monotonic()
        self._save_to_action()
        self._draw()
        self._status_var.set("Reset to linear")

    def _on_monotonic_toggle(self):
        self._push_undo()
        self._monotonic = self._mono_var.get()
        if self._monotonic:
            self._enforce_monotonic()
            self._save_to_action()
            self._draw()
            self._status_var.set(
                "Monotonic on — output increases with input")

    # ------------------------------------------------------------------
    # Import / Export / Copy
    # ------------------------------------------------------------------

    def _on_export(self):
        if self._mode not in ("spline", "segment"):
            return
        curve_type = "spline" if self._mode == "spline" else "segment"
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title=f"Export {curve_type.title()} Curve",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml *.yml"),
                       ("All files", "*.*")])
        if not path:
            return
        data = {"type": curve_type, "points": deepcopy(self._points)}
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        self._status_var.set(f"Exported to {path}")

    def _on_import(self):
        if self._mode not in ("spline", "segment"):
            return
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Import Curve",
            filetypes=[("YAML files", "*.yaml *.yml"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as exc:
            messagebox.showerror("Import Failed",
                                 f"Could not read YAML file:\n{exc}",
                                 parent=self.winfo_toplevel())
            return

        if isinstance(data, dict):
            points = data.get("points", [])
        elif isinstance(data, list):
            points = data
        else:
            messagebox.showerror(
                "Import Failed",
                "File does not contain curve data.",
                parent=self.winfo_toplevel())
            return

        if not points or not isinstance(points, list) or not all(
                isinstance(p, dict) and "x" in p and "y" in p
                for p in points):
            messagebox.showerror(
                "Import Failed",
                "Invalid point data. Each point must have 'x' and 'y'.",
                parent=self.winfo_toplevel())
            return

        self._push_undo()
        if self._mode == "spline":
            for p in points:
                if "tangent" not in p:
                    p["tangent"] = 1.0
            self._points = [dict(p) for p in points]
        else:
            self._points = [{"x": p["x"], "y": p["y"]} for p in points]
        self._points.sort(key=lambda p: p["x"])
        self._save_to_action()
        self._draw()
        self._status_var.set(f"Imported from {path}")

    def _on_copy_from(self):
        if self._mode not in ("spline", "segment"):
            return
        curves = {}
        if self._get_other_curves:
            curves = self._get_other_curves(self._mode)
        if not curves:
            self._status_var.set("No other curves available")
            return

        win = tk.Toplevel(self.winfo_toplevel())
        win.title("Copy Curve From...")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)

        ttk.Label(win, text="Select an action to copy its curve:",
                  padding=5).pack(anchor=tk.W)
        listbox = tk.Listbox(win, height=min(10, len(curves)), width=40)
        listbox.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        names = sorted(curves.keys())
        for name in names:
            listbox.insert(tk.END, name)

        def on_ok():
            sel = listbox.curselection()
            if not sel:
                return
            chosen = names[sel[0]]
            pts = curves[chosen]
            self._push_undo()
            if self._mode == "spline":
                for p in pts:
                    if "tangent" not in p:
                        p["tangent"] = 1.0
                self._points = [dict(p) for p in pts]
            else:
                self._points = [{"x": p["x"], "y": p["y"]} for p in pts]
            self._points.sort(key=lambda p: p["x"])
            self._save_to_action()
            self._draw()
            self._status_var.set(f"Copied curve from {chosen}")
            win.destroy()

        listbox.bind("<Double-1>", lambda e: on_ok())
        bf = ttk.Frame(win)
        bf.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(bf, text="OK", command=on_ok).pack(
            side=tk.RIGHT, padx=5)
        ttk.Button(bf, text="Cancel",
                   command=win.destroy).pack(side=tk.RIGHT)

        win.update_idletasks()
        px = self.winfo_toplevel().winfo_rootx()
        py = self.winfo_toplevel().winfo_rooty()
        pw = self.winfo_toplevel().winfo_width()
        ph = self.winfo_toplevel().winfo_height()
        ww, wh = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - ww) // 2}+{py + (ph - wh) // 2}")
