"""Interactive preview widget for the Action Editor tab.

Simulates the full analog shaping pipeline in real time with sliders,
a live output dot, and a decaying history trail.  Reuses the same
pipeline math as the robot code (utils/input/shaping.py and
utils/math/curves.py).  Supports controller input via XInput and a
2D position overlay for paired stick axes.
"""

import math
import tkinter as tk
from tkinter import ttk

from host.controller_config.gamepad_input import GamepadPoller
from utils.controller.model import (
    ActionDefinition,
    EventTriggerMode,
    InputType,
)
from utils.math.curves import evaluate_segments, evaluate_spline


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

_BG = "#ffffff"
_BG_INACTIVE = "#f0f0f0"
_GRID = "#e8e8e8"
_GRID_MAJOR = "#c8c8c8"
_AXIS = "#909090"
_LABEL = "#505050"
_DOT_COLOR = "#2060c0"
_DOT_OUTLINE = "#103060"
_TRAIL_NEWEST = (0x20, 0x60, 0xc0)   # bright blue
_TRAIL_OLDEST = (0xe0, 0xe0, 0xe0)   # near-white
_READOUT_FG = "#333333"

_DOT_RADIUS = 6
_TRAIL_MAX = 50
_TICK_MS = 20   # ~50 fps

# Motor visualization
_MOTOR_RADIUS = 18      # outer circle radius (px)
_MOTOR_DOT_RADIUS = 4   # rotating dot radius (px)
_MOTOR_MARGIN = 8       # padding from plot corner
_MOTOR_OUTLINE = "#808080"
_MOTOR_BG = "#f8f8f8"
_MOTOR_SPEED = 6 * math.pi  # rad/s at output = 1.0

# Axis-specific colors (used when both X and Y axes are active)
_X_AXIS_COLOR = "#2060c0"           # blue
_X_AXIS_OUTLINE = "#103060"
_X_TRAIL_NEWEST = (0x20, 0x60, 0xc0)
_X_TRAIL_OLDEST = (0xe0, 0xe0, 0xf0)
_Y_AXIS_COLOR = "#c04020"           # red
_Y_AXIS_OUTLINE = "#601810"
_Y_TRAIL_NEWEST = (0xc0, 0x40, 0x20)
_Y_TRAIL_OLDEST = (0xf0, 0xe0, 0xe0)

# 2D overlay inset
_OVERLAY_SIZE = 64       # inset square side length (px)
_OVERLAY_MARGIN = 8      # padding from plot corner
_OVERLAY_BG = "#f4f4f4"
_OVERLAY_BORDER = "#a0a0a0"
_OVERLAY_CROSSHAIR = "#d0d0d0"
_OVERLAY_DOT_COLOR = "#c04020"
_OVERLAY_DOT_RADIUS = 4
_OVERLAY_TRAIL_NEWEST = (0xc0, 0x40, 0x20)
_OVERLAY_TRAIL_OLDEST = (0xe8, 0xe0, 0xde)
_OVERLAY_TRAIL_MAX = 40
_OVERLAY_GRID_COLOR = "#b0c8e0"   # light blue for pipeline grid
_OVERLAY_GRID_SAMPLES = 30       # points per grid line

# Controller refresh interval (ms)
_CONTROLLER_REFRESH_MS = 2000

# Stick axis pairs (wpilib input names)
_STICK_PAIRS = {
    "left_stick_x": "left_stick_y",
    "left_stick_y": "left_stick_x",
    "right_stick_x": "right_stick_y",
    "right_stick_y": "right_stick_x",
}

# Vertical stick axes (primary bound to one of these → swap slider mapping)
_Y_AXES = {"left_stick_y", "right_stick_y"}


# ---------------------------------------------------------------------------
# SimpleSlewLimiter
# ---------------------------------------------------------------------------

class SimpleSlewLimiter:
    """Pure-python slew rate limiter matching wpimath.filter.SlewRateLimiter.

    Args:
        pos_rate: Max rate of increase per second (positive).
        neg_rate: Max rate of decrease per second (negative).
        dt: Time step per ``calculate()`` call (seconds).
    """

    def __init__(self, pos_rate: float, neg_rate: float, dt: float = 0.02):
        self._pos_rate = abs(pos_rate) if pos_rate else 0
        self._neg_rate = -abs(neg_rate) if neg_rate else 0
        self._dt = dt
        self._value = 0.0

    def calculate(self, input_val: float) -> float:
        delta = input_val - self._value
        if self._pos_rate > 0 and delta > 0:
            max_up = self._pos_rate * self._dt
            delta = min(delta, max_up)
        if self._neg_rate < 0 and delta < 0:
            max_down = self._neg_rate * self._dt
            delta = max(delta, max_down)
        self._value += delta
        return self._value

    def reset(self, value: float = 0.0):
        self._value = value


# ---------------------------------------------------------------------------
# Pure-python deadband (matches utils/input/shaping.py fallback)
# ---------------------------------------------------------------------------

def _apply_deadband(value: float, deadband: float) -> float:
    if abs(value) < deadband:
        return 0.0
    if value > 0:
        return (value - deadband) / (1.0 - deadband)
    return (value + deadband) / (1.0 - deadband)


# ---------------------------------------------------------------------------
# PreviewWidget
# ---------------------------------------------------------------------------

class PreviewWidget(ttk.Frame):
    """Interactive preview of the analog shaping pipeline.

    Shows a 2-D plot with:
    - X slider (horizontal) simulating the raw input (-1 to 1)
    - Y slider (vertical) for paired axis / 2-axis preview
    - A dot at the current (input, output) position
    - A fading history trail of recent positions
    - Output readout label
    - Input source dropdown (Manual sliders or XInput controllers)
    - 2D position overlay when paired stick axes are available
    """

    def __init__(self, parent):
        super().__init__(parent)

        self._action: ActionDefinition | None = None
        self._qname: str | None = None

        # Pipeline closure: float -> float (None = inactive)
        self._pipeline = None
        self._slew: SimpleSlewLimiter | None = None

        # Canvas sizing
        self._margin_x = 35
        self._margin_y = 30
        self._plot_w = 0
        self._plot_h = 0

        # X-axis range: -1..1 for sticks, 0..1 for triggers
        self._x_min = -1.0

        # Y-axis range: auto-scaled from pipeline output
        self._y_min = -1.0
        self._y_max = 1.0

        # History trail ring buffer: list of (input_x, output_y)
        self._trail: list[tuple[float, float]] = []

        # Animation state
        self._tick_id = None
        self._last_input = 0.0
        self._last_output = 0.0
        self._syncing_slider = False   # guard against slider sync loops

        # Motor visualization angles (radians) — separate for X and Y axes
        self._x_motor_angle = 0.0
        self._y_motor_angle = 0.0

        # --- Controller input ---
        self._gamepad = GamepadPoller()
        self._input_mode = "manual"   # "manual" or int (controller index)

        # Binding details: [(port, input_name), ...]
        self._binding_details: list[tuple[int, str]] = []
        # Primary binding for controller reading
        self._primary_input_name: str | None = None
        # True when primary axis is vertical (left_stick_y, right_stick_y)
        # — used to swap slider/overlay mapping in controller mode
        self._primary_is_y = False

        # --- Paired axis / 2D overlay ---
        self._paired_action: ActionDefinition | None = None
        self._paired_qname: str | None = None
        self._paired_pipeline = None
        self._paired_slew: SimpleSlewLimiter | None = None
        self._paired_input_name: str | None = None
        self._paired_trail: list[tuple[float, float]] = []
        self._paired_1d_trail: list[tuple[float, float]] = []
        self._last_paired_input = 0.0
        self._last_paired_output = 0.0

        # Controller list refresh timer
        self._controller_refresh_id = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Main area: Y slider | canvas over X slider
        plot_area = ttk.Frame(self)
        plot_area.pack(fill=tk.BOTH, expand=True)

        # Y slider (left)
        self._y_slider = tk.Scale(
            plot_area, from_=-1.0, to=1.0, resolution=0.01,
            orient=tk.VERTICAL, showvalue=False, length=100,
            sliderlength=12, width=14,
            command=self._on_y_slider)
        self._y_slider.set(0.0)
        self._y_slider.pack(side=tk.LEFT, fill=tk.Y, padx=(2, 0), pady=2)

        # Right side: canvas + X slider stacked
        right = ttk.Frame(plot_area)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(right, bg=_BG_INACTIVE,
                                 highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=(0, 2), pady=(2, 0))
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # X slider (below canvas)
        self._x_slider = tk.Scale(
            right, from_=-1.0, to=1.0, resolution=0.01,
            orient=tk.HORIZONTAL, showvalue=False,
            sliderlength=12, width=14,
            command=self._on_x_slider)
        self._x_slider.set(0.0)
        self._x_slider.pack(fill=tk.X, padx=(0, 2), pady=(0, 2))

        # Readout label
        self._readout_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._readout_var,
                  font=("TkFixedFont", 8), anchor=tk.CENTER,
                  foreground=_READOUT_FG).pack(fill=tk.X, padx=4)

        # Input source selector (replaces NT connection placeholder)
        input_frame = ttk.Frame(self, padding=(4, 2))
        input_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

        ttk.Label(input_frame, text="Input:",
                  font=("TkDefaultFont", 8)).pack(side=tk.LEFT, padx=(0, 4))

        self._input_source_var = tk.StringVar(value="Manual (Sliders)")
        self._input_combo = ttk.Combobox(
            input_frame, textvariable=self._input_source_var,
            state="readonly", font=("TkDefaultFont", 8), width=20)
        self._input_combo["values"] = ["Manual (Sliders)"]
        self._input_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._input_combo.bind(
            "<<ComboboxSelected>>", self._on_input_source_changed)

        # Synced checkbox — locks X and Y sliders together in manual mode
        self._sync_var = tk.BooleanVar(value=True)
        self._sync_check = ttk.Checkbutton(
            input_frame, text="Synced", variable=self._sync_var,
            style="TCheckbutton")
        self._sync_check.pack(side=tk.LEFT, padx=(6, 0))

        # Start periodic controller refresh
        self._schedule_controller_refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Input names that only produce 0..1 (Xbox triggers)
    _TRIGGER_INPUTS = {"left_trigger", "right_trigger"}

    def load_action(self, action: ActionDefinition, qname: str,
                    bound_inputs: list[str] | None = None,
                    binding_details: list[tuple[int, str]] | None = None,
                    paired_action_info: tuple | None = None):
        """Load an action and start the preview if it's analog.

        Args:
            bound_inputs: list of input names bound to this action.
                If any are trigger inputs (0..1 range), the X axis
                adjusts from -1..1 to 0..1.
            binding_details: list of (port, input_name) tuples for
                controller input and paired axis detection.
            paired_action_info: (ActionDefinition, qname) for the
                paired stick axis action, or None.
        """
        self._action = action
        self._qname = qname
        self._trail.clear()
        self._x_motor_angle = 0.0
        self._y_motor_angle = 0.0

        # Store binding info
        self._binding_details = binding_details or []
        self._primary_input_name = None
        self._paired_input_name = None
        self._primary_is_y = False
        if self._binding_details:
            _, inp = self._binding_details[0]
            self._primary_input_name = inp
            self._primary_is_y = inp in _Y_AXES
            paired = _STICK_PAIRS.get(inp)
            if paired:
                self._paired_input_name = paired

        # Store paired action
        if paired_action_info:
            self._paired_action, self._paired_qname = paired_action_info
        else:
            self._paired_action = None
            self._paired_qname = None
        self._paired_trail.clear()
        self._paired_1d_trail.clear()
        self._last_paired_input = 0.0
        self._last_paired_output = 0.0

        # Detect trigger-range inputs
        self._update_x_range(bound_inputs)
        self._build_pipeline()
        self._build_paired_pipeline()

        if self._pipeline:
            self._canvas.config(bg=_BG)
            self._start_tick()
        else:
            self._stop_tick()
            self._canvas.config(bg=_BG_INACTIVE)
            self._draw_inactive_message()
            self._readout_var.set("")

    def clear(self):
        """Clear preview (no action selected)."""
        self._action = None
        self._qname = None
        self._pipeline = None
        self._slew = None
        self._trail.clear()
        self._binding_details = []
        self._primary_input_name = None
        self._paired_action = None
        self._paired_qname = None
        self._paired_pipeline = None
        self._paired_slew = None
        self._paired_input_name = None
        self._paired_trail.clear()
        self._paired_1d_trail.clear()
        self._last_paired_input = 0.0
        self._last_paired_output = 0.0
        self._stop_tick()
        self._canvas.config(bg=_BG_INACTIVE)
        self._draw_inactive_message()
        self._readout_var.set("")

    def refresh(self):
        """Rebuild pipeline from current action params (field changed)."""
        if not self._action:
            return
        self._trail.clear()
        self._paired_trail.clear()
        self._paired_1d_trail.clear()
        self._build_pipeline()
        self._build_paired_pipeline()
        if self._pipeline:
            self._canvas.config(bg=_BG)
            self._start_tick()
        else:
            self._stop_tick()
            self._canvas.config(bg=_BG_INACTIVE)
            self._draw_inactive_message()
            self._readout_var.set("")

    def update_bindings(self, bound_inputs: list[str] | None = None,
                        binding_details: list[tuple[int, str]] | None = None,
                        paired_action_info: tuple | None = None):
        """Update when bindings change (assign/unassign)."""
        old_x_min = self._x_min

        # Update binding details
        self._binding_details = binding_details or []
        self._primary_input_name = None
        self._paired_input_name = None
        self._primary_is_y = False
        if self._binding_details:
            _, inp = self._binding_details[0]
            self._primary_input_name = inp
            self._primary_is_y = inp in _Y_AXES
            paired = _STICK_PAIRS.get(inp)
            if paired:
                self._paired_input_name = paired

        # Update paired action
        if paired_action_info:
            self._paired_action, self._paired_qname = paired_action_info
        else:
            self._paired_action = None
            self._paired_qname = None
        self._paired_trail.clear()
        self._paired_1d_trail.clear()
        self._build_paired_pipeline()

        self._update_x_range(bound_inputs)
        if self._x_min != old_x_min:
            self._trail.clear()
            self._build_pipeline()
            if self._pipeline:
                self._draw()

    def _update_x_range(self, bound_inputs: list[str] | None):
        """Set X range based on bound input types.

        If ALL bound inputs are triggers (0..1), use 0..1.
        Otherwise use -1..1 (sticks, or no bindings).
        """
        if bound_inputs and all(
                inp in self._TRIGGER_INPUTS for inp in bound_inputs):
            new_min = 0.0
        else:
            new_min = -1.0

        if new_min != self._x_min:
            self._x_min = new_min
            # Update slider ranges
            self._syncing_slider = True
            self._x_slider.config(from_=new_min)
            self._y_slider.config(from_=new_min)
            # Clamp current value into range
            cur = self._x_slider.get()
            if cur < new_min:
                self._x_slider.set(new_min)
                self._y_slider.set(new_min)
            self._syncing_slider = False

    # ------------------------------------------------------------------
    # Pipeline Construction
    # ------------------------------------------------------------------

    @staticmethod
    def _make_pipeline_fn(action: ActionDefinition):
        """Build a shaping closure from action parameters.

        Returns (pipeline_fn, is_raw).  Returns (None, False) when
        the action is not ANALOG.
        """
        if not action or action.input_type != InputType.ANALOG:
            return None, False

        mode = action.trigger_mode
        if mode == EventTriggerMode.RAW:
            return (lambda raw: raw), True

        inversion = action.inversion
        deadband = action.deadband
        scale = action.scale
        extra = action.extra or {}
        spline_pts = extra.get("spline_points")
        segment_pts = extra.get("segment_points")

        if mode == EventTriggerMode.SQUARED:
            def pipeline(raw):
                v = -raw if inversion else raw
                v = _apply_deadband(v, deadband) if deadband > 0 else v
                v = math.copysign(v * v, v)
                return v * scale
        elif mode == EventTriggerMode.SPLINE and spline_pts:
            def pipeline(raw):
                v = -raw if inversion else raw
                v = _apply_deadband(v, deadband) if deadband > 0 else v
                v = evaluate_spline(spline_pts, v)
                return v * scale
        elif mode == EventTriggerMode.SEGMENTED and segment_pts:
            def pipeline(raw):
                v = -raw if inversion else raw
                v = _apply_deadband(v, deadband) if deadband > 0 else v
                v = evaluate_segments(segment_pts, v)
                return v * scale
        else:
            # SCALED (and fallback)
            def pipeline(raw):
                v = -raw if inversion else raw
                v = _apply_deadband(v, deadband) if deadband > 0 else v
                return v * scale

        return pipeline, False

    @staticmethod
    def _make_slew_limiter(action: ActionDefinition):
        """Build a SimpleSlewLimiter from action params, or None."""
        slew_rate = action.slew_rate
        if slew_rate > 0:
            extra = action.extra or {}
            neg_rate = extra.get("negative_slew_rate")
            if neg_rate is None:
                neg_rate = -slew_rate
            else:
                neg_rate = float(neg_rate)
            return SimpleSlewLimiter(
                slew_rate, neg_rate, dt=_TICK_MS / 1000.0)
        return None

    def _build_pipeline(self):
        """Build the primary shaping pipeline from the current action."""
        self._pipeline, is_raw = self._make_pipeline_fn(self._action)
        if self._pipeline is None:
            self._slew = None
            return
        if is_raw:
            self._y_min = -1.0
            self._y_max = 1.0
            self._slew = None
            return
        self._compute_y_range()
        self._slew = self._make_slew_limiter(self._action)

    def _build_paired_pipeline(self):
        """Build a pipeline for the paired stick axis.

        If a paired action exists, build its full shaping pipeline.
        If no paired action but the input is a stick axis, use passthrough
        so the 2D overlay still shows raw paired-axis values.
        Recomputes Y range so both pipelines fit on the 1D plot.
        """
        if self._paired_action:
            self._paired_pipeline, is_raw = self._make_pipeline_fn(
                self._paired_action)
            if self._paired_pipeline and not is_raw:
                self._paired_slew = self._make_slew_limiter(
                    self._paired_action)
            else:
                self._paired_slew = None
        elif self._paired_input_name:
            # Stick axis with no paired action — passthrough
            self._paired_pipeline = lambda raw: raw
            self._paired_slew = None
        else:
            self._paired_pipeline = None
            self._paired_slew = None
        # Recompute Y range to include both pipelines
        if self._pipeline:
            self._compute_y_range()

    _Y_RANGE_SAMPLES = 200

    def _compute_y_range(self):
        """Auto-scale Y axis by sampling pipeline output across x range.

        Also samples the paired pipeline so both curves fit on the plot.
        """
        if not self._pipeline:
            self._y_min = -1.0
            self._y_max = 1.0
            return
        y_min = 0.0
        y_max = 0.0
        n = self._Y_RANGE_SAMPLES
        x_span = 1.0 - self._x_min
        pipelines = [self._pipeline]
        if self._paired_pipeline:
            pipelines.append(self._paired_pipeline)
        for pipe in pipelines:
            for i in range(n + 1):
                x = self._x_min + x_span * i / n
                y = pipe(x)
                y_min = min(y_min, y)
                y_max = max(y_max, y)
        # Ensure range always includes at least -1..1
        y_min = min(y_min, -1.0)
        y_max = max(y_max, 1.0)
        pad = (y_max - y_min) * 0.05
        self._y_min = y_min - pad
        self._y_max = y_max + pad

    @staticmethod
    def _nice_grid_step(span: float) -> float:
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

    # ------------------------------------------------------------------
    # Canvas Sizing & Coordinate Conversion
    # ------------------------------------------------------------------

    def _on_canvas_configure(self, event):
        w, h = event.width, event.height
        if w < 20 or h < 20:
            return

        mx = max(25, min(50, int(w * 0.08)))
        my = max(25, min(50, int(h * 0.08)))
        self._margin_x = mx
        self._margin_y = my
        self._plot_w = max(10, w - 2 * mx)
        self._plot_h = max(10, h - 2 * my)

        if self._pipeline:
            self._draw()
        else:
            self._draw_inactive_message()

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
        """Canvas pixel coords to data coords."""
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

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self):
        """Full redraw: grid, trail, current dot."""
        c = self._canvas
        c.delete("all")
        if self._plot_w < 10:
            return

        self._draw_grid()
        self._draw_trail()
        self._draw_current()
        self._draw_motors()
        if self._paired_pipeline:
            self._draw_2d_overlay()
            self._draw_legend()

    def _draw_inactive_message(self):
        """Show an inactive placeholder message."""
        c = self._canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return

        if not self._action:
            msg = "Select an action"
        elif self._action.input_type == InputType.BUTTON:
            msg = "Button \u2014 no analog preview"
        elif self._action.input_type == InputType.OUTPUT:
            msg = "Output \u2014 no analog preview"
        else:
            msg = "No preview available"
        c.create_text(w // 2, h // 2, text=msg,
                      fill="#888888", font=("TkDefaultFont", 10))

    def _draw_grid(self):
        """Draw gridlines and axis labels (dynamic Y range)."""
        c = self._canvas
        mx = self._margin_x
        my = self._margin_y
        pw = self._plot_w
        ph = self._plot_h
        font = ("TkDefaultFont", 7)

        # X gridlines (dynamic based on x_min)
        if self._x_min >= 0:
            x_vals = [0.0, 0.25, 0.5, 0.75, 1.0]
        else:
            x_vals = [-1.0, -0.5, 0.0, 0.5, 1.0]
        for v in x_vals:
            cx, _ = self._d2c(v, 0)
            is_axis = abs(v) < 0.01
            is_boundary = abs(v - self._x_min) < 0.01 or abs(v - 1.0) < 0.01
            color = _AXIS if is_axis else (
                _GRID_MAJOR if is_boundary else _GRID)
            w = 1.5 if is_axis else 1
            c.create_line(cx, my, cx, my + ph, fill=color, width=w)

        # Y gridlines (dynamic range)
        y_step = self._nice_grid_step(self._y_max - self._y_min)
        y_start = math.floor(self._y_min / y_step) * y_step
        v = y_start
        while v <= self._y_max + y_step * 0.01:
            _, cy = self._d2c(0, v)
            is_axis = abs(v) < y_step * 0.01
            color = _AXIS if is_axis else _GRID_MAJOR
            w = 1.5 if is_axis else 1
            c.create_line(mx, cy, mx + pw, cy, fill=color, width=w)
            v += y_step

        # X labels (below)
        for v in x_vals:
            cx, _ = self._d2c(v, 0)
            c.create_text(cx, my + ph + 12,
                          text=f"{v:g}", fill=_LABEL, font=font)

        # Y labels (left, dynamic)
        v = y_start
        while v <= self._y_max + y_step * 0.01:
            _, cy = self._d2c(0, v)
            c.create_text(mx - 18, cy,
                          text=f"{v:g}", fill=_LABEL, font=font)
            v += y_step

        # Reference lines at +/-1 when Y extends beyond
        if self._y_min < -1.05 or self._y_max > 1.05:
            for ref_y in (-1.0, 1.0):
                _, ry = self._d2c(0, ref_y)
                c.create_line(mx, ry, mx + pw, ry,
                              fill="#b0b0ff", width=1, dash=(6, 3))

        # Border
        c.create_rectangle(mx, my, mx + pw, my + ph, outline="#808080")

    def _draw_trail_data(self, trail, newest_color, oldest_color):
        """Draw a fading trail from oldest (dim) to newest (bright)."""
        c = self._canvas
        n = len(trail)
        if n == 0:
            return
        for i, (tx, ty) in enumerate(trail):
            frac = i / max(n - 1, 1)
            r = int(oldest_color[0] + frac * (
                newest_color[0] - oldest_color[0]))
            g = int(oldest_color[1] + frac * (
                newest_color[1] - oldest_color[1]))
            b = int(oldest_color[2] + frac * (
                newest_color[2] - oldest_color[2]))
            color = f"#{r:02x}{g:02x}{b:02x}"
            cx, cy = self._d2c(tx, ty)
            radius = 2 + frac * 2
            c.create_oval(cx - radius, cy - radius,
                          cx + radius, cy + radius,
                          fill=color, outline="")

    def _draw_trail(self):
        """Draw fading history dots for primary and paired pipelines."""
        if self._paired_pipeline:
            if self._primary_is_y:
                prim_new, prim_old = _Y_TRAIL_NEWEST, _Y_TRAIL_OLDEST
                pair_new, pair_old = _X_TRAIL_NEWEST, _X_TRAIL_OLDEST
            else:
                prim_new, prim_old = _X_TRAIL_NEWEST, _X_TRAIL_OLDEST
                pair_new, pair_old = _Y_TRAIL_NEWEST, _Y_TRAIL_OLDEST
            self._draw_trail_data(
                self._paired_1d_trail, pair_new, pair_old)
            self._draw_trail_data(self._trail, prim_new, prim_old)
        else:
            self._draw_trail_data(
                self._trail, _TRAIL_NEWEST, _TRAIL_OLDEST)

    def _draw_current(self):
        """Draw the large dot at current (input, output)."""
        c = self._canvas
        if self._paired_pipeline:
            if self._primary_is_y:
                prim_fill, prim_out = _Y_AXIS_COLOR, _Y_AXIS_OUTLINE
                pair_fill, pair_out = _X_AXIS_COLOR, _X_AXIS_OUTLINE
            else:
                prim_fill, prim_out = _X_AXIS_COLOR, _X_AXIS_OUTLINE
                pair_fill, pair_out = _Y_AXIS_COLOR, _Y_AXIS_OUTLINE
            # Paired dot (draw first so primary is on top)
            px, py = self._d2c(
                self._last_paired_input, self._last_paired_output)
            c.create_oval(px - _DOT_RADIUS, py - _DOT_RADIUS,
                          px + _DOT_RADIUS, py + _DOT_RADIUS,
                          fill=pair_fill, outline=pair_out, width=1.5)
            # Primary dot
            cx, cy = self._d2c(self._last_input, self._last_output)
            c.create_oval(cx - _DOT_RADIUS, cy - _DOT_RADIUS,
                          cx + _DOT_RADIUS, cy + _DOT_RADIUS,
                          fill=prim_fill, outline=prim_out, width=1.5)
        else:
            cx, cy = self._d2c(self._last_input, self._last_output)
            c.create_oval(cx - _DOT_RADIUS, cy - _DOT_RADIUS,
                          cx + _DOT_RADIUS, cy + _DOT_RADIUS,
                          fill=_DOT_COLOR, outline=_DOT_OUTLINE, width=1.5)

    def _draw_motor_at(self, cx, cy, angle, label, color):
        """Draw a spinning motor indicator at the given center position."""
        c = self._canvas

        # Outer circle
        c.create_oval(
            cx - _MOTOR_RADIUS, cy - _MOTOR_RADIUS,
            cx + _MOTOR_RADIUS, cy + _MOTOR_RADIUS,
            outline=_MOTOR_OUTLINE, fill=_MOTOR_BG, width=1.5)

        # Rotating dot on the rim
        orbit_r = _MOTOR_RADIUS - _MOTOR_DOT_RADIUS - 2
        dot_x = cx + orbit_r * math.cos(angle)
        dot_y = cy + orbit_r * math.sin(angle)
        c.create_oval(
            dot_x - _MOTOR_DOT_RADIUS, dot_y - _MOTOR_DOT_RADIUS,
            dot_x + _MOTOR_DOT_RADIUS, dot_y + _MOTOR_DOT_RADIUS,
            fill=color, outline="")

        # Label above motor
        c.create_text(cx, cy - _MOTOR_RADIUS - 6, text=label,
                      fill=color, font=("TkDefaultFont", 7))

    def _draw_motors(self):
        """Draw X and Y motor indicators when their axes are active."""
        mx = self._margin_x
        my = self._margin_y
        pw = self._plot_w
        ph = self._plot_h

        # Determine which axes have active outputs
        both = self._paired_pipeline is not None
        if self._primary_is_y:
            y_active = self._pipeline is not None
            x_active = both
        else:
            x_active = self._pipeline is not None
            y_active = both

        # Right motor (X axis) — bottom-right corner
        if x_active:
            rcx = mx + pw - _MOTOR_RADIUS - _MOTOR_MARGIN
            rcy = my + ph - _MOTOR_RADIUS - _MOTOR_MARGIN
            x_color = _X_AXIS_COLOR if both else _DOT_COLOR
            self._draw_motor_at(
                rcx, rcy, self._x_motor_angle, "X", x_color)

        # Left motor (Y axis) — bottom-left corner
        if y_active:
            lcx = mx + _MOTOR_RADIUS + _MOTOR_MARGIN
            lcy = my + ph - _MOTOR_RADIUS - _MOTOR_MARGIN
            y_color = _Y_AXIS_COLOR if both else _DOT_COLOR
            self._draw_motor_at(
                lcx, lcy, self._y_motor_angle, "Y", y_color)

    def _draw_legend(self):
        """Draw axis color legend in top-right corner of plot."""
        c = self._canvas
        mx = self._margin_x
        my = self._margin_y
        pw = self._plot_w
        font = ("TkDefaultFont", 7)
        dot_r = 3
        line_h = 12
        pad = 6

        # Position: top-right corner, inset
        rx = mx + pw - pad
        ry = my + pad

        # X axis entry (blue)
        c.create_oval(rx - 40 - dot_r, ry - dot_r,
                      rx - 40 + dot_r, ry + dot_r,
                      fill=_X_AXIS_COLOR, outline="")
        c.create_text(rx - 40 + dot_r + 4, ry, text="X axis",
                      anchor=tk.W, fill=_X_AXIS_COLOR, font=font)

        # Y axis entry (red)
        ry2 = ry + line_h
        c.create_oval(rx - 40 - dot_r, ry2 - dot_r,
                      rx - 40 + dot_r, ry2 + dot_r,
                      fill=_Y_AXIS_COLOR, outline="")
        c.create_text(rx - 40 + dot_r + 4, ry2, text="Y axis",
                      anchor=tk.W, fill=_Y_AXIS_COLOR, font=font)

    def _draw_2d_overlay(self):
        """Draw 2D position inset in top-left of plot area."""
        c = self._canvas
        mx = self._margin_x
        my = self._margin_y
        size = _OVERLAY_SIZE

        # Inset position: top-left corner
        ox = mx + _OVERLAY_MARGIN
        oy = my + _OVERLAY_MARGIN

        # Background
        c.create_rectangle(ox, oy, ox + size, oy + size,
                           fill=_OVERLAY_BG, outline=_OVERLAY_BORDER,
                           width=1)

        # Crosshair at center
        cx_center = ox + size / 2
        cy_center = oy + size / 2
        c.create_line(ox + 2, cy_center, ox + size - 2, cy_center,
                      fill=_OVERLAY_CROSSHAIR, width=1)
        c.create_line(cx_center, oy + 2, cx_center, oy + size - 2,
                      fill=_OVERLAY_CROSSHAIR, width=1)

        # Map -1..1 to overlay pixel coords
        def ov_xy(xv, yv):
            px = ox + (xv + 1.0) / 2.0 * size
            py = oy + (1.0 - (yv + 1.0) / 2.0) * size
            return px, py

        # Determine which pipeline maps to X vs Y in the overlay
        if self._primary_is_y:
            x_pipe = self._paired_pipeline
            y_pipe = self._pipeline
        else:
            x_pipe = self._pipeline
            y_pipe = self._paired_pipeline

        # Draw warped grid showing both pipeline responses (static,
        # no slew).  Vertical grid lines: fixed x input, sweep y.
        # Horizontal grid lines: fixed y input, sweep x.
        n = _OVERLAY_GRID_SAMPLES
        grid_vals = [-1.0, -0.5, 0.0, 0.5, 1.0]

        for gx in grid_vals:
            x_out = x_pipe(gx)
            pts = []
            for i in range(n + 1):
                y_in = -1.0 + 2.0 * i / n
                y_out = y_pipe(y_in)
                pts.extend(ov_xy(x_out, y_out))
            if len(pts) >= 4:
                c.create_line(*pts, fill=_OVERLAY_GRID_COLOR, width=1)

        for gy in grid_vals:
            y_out = y_pipe(gy)
            pts = []
            for i in range(n + 1):
                x_in = -1.0 + 2.0 * i / n
                x_out = x_pipe(x_in)
                pts.extend(ov_xy(x_out, y_out))
            if len(pts) >= 4:
                c.create_line(*pts, fill=_OVERLAY_GRID_COLOR, width=1)

        # Trail
        n_trail = len(self._paired_trail)
        for i, (tx, ty) in enumerate(self._paired_trail):
            frac = i / max(n_trail - 1, 1)
            r = int(_OVERLAY_TRAIL_OLDEST[0] + frac * (
                _OVERLAY_TRAIL_NEWEST[0] - _OVERLAY_TRAIL_OLDEST[0]))
            g = int(_OVERLAY_TRAIL_OLDEST[1] + frac * (
                _OVERLAY_TRAIL_NEWEST[1] - _OVERLAY_TRAIL_OLDEST[1]))
            b = int(_OVERLAY_TRAIL_OLDEST[2] + frac * (
                _OVERLAY_TRAIL_NEWEST[2] - _OVERLAY_TRAIL_OLDEST[2]))
            color = f"#{r:02x}{g:02x}{b:02x}"
            px, py = ov_xy(tx, ty)
            radius = 1 + frac
            c.create_oval(px - radius, py - radius,
                          px + radius, py + radius,
                          fill=color, outline="")

        # Current dot — use correct physical mapping
        if self._primary_is_y:
            px, py = ov_xy(self._last_paired_output, self._last_output)
        else:
            px, py = ov_xy(self._last_output, self._last_paired_output)
        c.create_oval(
            px - _OVERLAY_DOT_RADIUS, py - _OVERLAY_DOT_RADIUS,
            px + _OVERLAY_DOT_RADIUS, py + _OVERLAY_DOT_RADIUS,
            fill=_OVERLAY_DOT_COLOR, outline="")

        # Label — show stick name if known
        if self._primary_input_name and "left" in self._primary_input_name:
            label = "L Stick"
        elif self._primary_input_name and "right" in self._primary_input_name:
            label = "R Stick"
        else:
            label = "2D"
        c.create_text(ox + 3, oy + 3, text=label, anchor=tk.NW,
                      fill=_OVERLAY_BORDER, font=("TkDefaultFont", 6))

    # ------------------------------------------------------------------
    # Slider Callbacks
    # ------------------------------------------------------------------

    def _on_x_slider(self, val):
        """X slider changed — sync Y slider when synced."""
        if self._syncing_slider:
            return
        if self._sync_var.get():
            self._syncing_slider = True
            self._y_slider.set(float(val))
            self._syncing_slider = False

    def _on_y_slider(self, val):
        """Y slider changed — sync X slider when synced."""
        if self._syncing_slider:
            return
        if self._sync_var.get():
            self._syncing_slider = True
            self._x_slider.set(float(val))
            self._syncing_slider = False

    # ------------------------------------------------------------------
    # Input Source Management
    # ------------------------------------------------------------------

    def _on_input_source_changed(self, event=None):
        """Handle input source dropdown selection."""
        selection = self._input_source_var.get()
        if selection.startswith("Controller"):
            try:
                idx = int(selection.split()[1].rstrip(":"))
                self._input_mode = idx
            except (ValueError, IndexError):
                self._input_mode = "manual"
        else:
            self._input_mode = "manual"
        # Grey out sync checkbox on controller, enable on manual
        if self._input_mode == "manual":
            self._sync_check.state(["!disabled"])
        else:
            self._sync_check.state(["disabled"])
        # Clear trails when switching input source
        self._trail.clear()
        self._paired_trail.clear()
        self._paired_1d_trail.clear()
        if self._slew:
            self._slew.reset()
        if self._paired_slew:
            self._paired_slew.reset()

    def _schedule_controller_refresh(self):
        """Schedule periodic controller enumeration."""
        self._refresh_controller_list()
        self._controller_refresh_id = self.after(
            _CONTROLLER_REFRESH_MS, self._schedule_controller_refresh)

    def _refresh_controller_list(self):
        """Update the input source dropdown with connected controllers."""
        values = ["Manual (Sliders)"]
        if self._gamepad.available:
            for idx in self._gamepad.get_connected():
                values.append(f"Controller {idx}")
        else:
            values.append("(Install XInput-Python for gamepad)")

        current = self._input_source_var.get()
        self._input_combo["values"] = values

        # If currently selected controller disconnected, fall back
        if current not in values:
            self._input_source_var.set("Manual (Sliders)")
            self._input_mode = "manual"

    # ------------------------------------------------------------------
    # Animation Loop
    # ------------------------------------------------------------------

    def _start_tick(self):
        """Start the animation loop if not already running."""
        if self._tick_id is None:
            self._tick()

    def _stop_tick(self):
        """Stop the animation loop."""
        if self._tick_id is not None:
            self.after_cancel(self._tick_id)
            self._tick_id = None

    def _tick(self):
        """One animation frame: compute output, update trail, redraw."""
        if not self._pipeline:
            self._tick_id = None
            return

        # --- Read primary input ---
        controller_active = (
            self._input_mode != "manual"
            and self._primary_input_name
            and self._gamepad.available)

        if controller_active:
            # Controller mode: read axis from gamepad
            raw_input = self._gamepad.get_axis(
                self._input_mode, self._primary_input_name)
            # Sync slider to show controller value.
            # If primary is a Y-type axis (e.g. left_stick_y), show it on
            # the vertical slider; otherwise on the horizontal slider.
            self._syncing_slider = True
            if self._primary_is_y:
                self._y_slider.set(raw_input)
            else:
                self._x_slider.set(raw_input)
            self._syncing_slider = False
        else:
            # Manual mode: read from X slider (primary input)
            raw_input = self._x_slider.get()

        # Run through shaping pipeline
        shaped = self._pipeline(raw_input)

        # Apply slew rate limiter
        if self._slew:
            output = self._slew.calculate(shaped)
        else:
            output = shaped

        self._last_input = raw_input
        self._last_output = output

        # Advance motor angles: output=1 → full speed
        dt = _TICK_MS / 1000.0
        if self._primary_is_y:
            self._y_motor_angle += output * _MOTOR_SPEED * dt
        else:
            self._x_motor_angle += output * _MOTOR_SPEED * dt

        # Append to trail
        self._trail.append((raw_input, output))
        if len(self._trail) > _TRAIL_MAX:
            self._trail.pop(0)

        # --- Paired axis (2D overlay) ---
        if self._paired_pipeline:
            if controller_active and self._paired_input_name:
                y_raw = self._gamepad.get_axis(
                    self._input_mode, self._paired_input_name)
                # Put paired axis on the opposite slider
                self._syncing_slider = True
                if self._primary_is_y:
                    self._x_slider.set(y_raw)
                else:
                    self._y_slider.set(y_raw)
                self._syncing_slider = False
            else:
                y_raw = self._y_slider.get()

            y_shaped = self._paired_pipeline(y_raw)
            if self._paired_slew:
                y_out = self._paired_slew.calculate(y_shaped)
            else:
                y_out = y_shaped
            self._last_paired_input = y_raw
            self._last_paired_output = y_out

            # Append to 1D trail for paired pipeline
            self._paired_1d_trail.append((y_raw, y_out))
            if len(self._paired_1d_trail) > _TRAIL_MAX:
                self._paired_1d_trail.pop(0)

            # Advance the paired axis motor angle
            if self._primary_is_y:
                self._x_motor_angle += y_out * _MOTOR_SPEED * dt
            else:
                self._y_motor_angle += y_out * _MOTOR_SPEED * dt

            # Store trail with correct physical mapping:
            # (x_value, y_value) where x=horizontal, y=vertical
            if self._primary_is_y:
                self._paired_trail.append((y_out, output))
            else:
                self._paired_trail.append((output, y_out))
            if len(self._paired_trail) > _OVERLAY_TRAIL_MAX:
                self._paired_trail.pop(0)

        # Update readout
        if self._paired_pipeline:
            pi = self._last_paired_input
            po = self._last_paired_output
            if self._primary_is_y:
                self._readout_var.set(
                    f"X: {pi:+.3f}\u2192{po:+.3f}  "
                    f"Y: {raw_input:+.3f}\u2192{output:+.3f}")
            else:
                self._readout_var.set(
                    f"X: {raw_input:+.3f}\u2192{output:+.3f}  "
                    f"Y: {pi:+.3f}\u2192{po:+.3f}")
        else:
            self._readout_var.set(
                f"In: {raw_input:+.3f}  \u2192  Out: {output:+.3f}")

        # Redraw
        self._draw()

        # Schedule next tick
        self._tick_id = self.after(_TICK_MS, self._tick)
