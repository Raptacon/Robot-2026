"""Interactive preview widget for the Action Editor tab.

Simulates the full analog shaping pipeline in real time with sliders,
a live output dot, and a decaying history trail.  Reuses the same
pipeline math as the robot code (utils/input/shaping.py and
utils/math/curves.py).
"""

import math
import tkinter as tk
from tkinter import ttk

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
_MOTOR_DOT_COLOR = "#2060c0"
_MOTOR_SPEED = 6 * math.pi  # rad/s at output = 1.0


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
    - Y slider (vertical) for future 2-axis preview
    - A dot at the current (input, output) position
    - A fading history trail of recent positions
    - Output readout label
    - NT connection placeholder at the bottom
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

        # Motor visualization angle (radians)
        self._motor_angle = 0.0

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

        # NT connection placeholder
        nt_frame = ttk.LabelFrame(self, text="NT Connection", padding=4)
        nt_frame.pack(fill=tk.X, padx=4, pady=(2, 4))

        self._nt_status = ttk.Label(
            nt_frame, text="Future feature — push/pull config via NT",
            foreground="#888888", font=("TkDefaultFont", 8))
        self._nt_status.pack(anchor=tk.W)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Input names that only produce 0..1 (Xbox triggers)
    _TRIGGER_INPUTS = {"left_trigger", "right_trigger"}

    def load_action(self, action: ActionDefinition, qname: str,
                    bound_inputs: list[str] | None = None):
        """Load an action and start the preview if it's analog.

        Args:
            bound_inputs: list of input names bound to this action.
                If any are trigger inputs (0..1 range), the X axis
                adjusts from -1..1 to 0..1.
        """
        self._action = action
        self._qname = qname
        self._trail.clear()
        self._motor_angle = 0.0

        # Detect trigger-range inputs
        self._update_x_range(bound_inputs)
        self._build_pipeline()

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
        self._stop_tick()
        self._canvas.config(bg=_BG_INACTIVE)
        self._draw_inactive_message()
        self._readout_var.set("")

    def refresh(self):
        """Rebuild pipeline from current action params (field changed)."""
        if not self._action:
            return
        self._trail.clear()
        self._build_pipeline()
        if self._pipeline:
            self._canvas.config(bg=_BG)
            self._start_tick()
        else:
            self._stop_tick()
            self._canvas.config(bg=_BG_INACTIVE)
            self._draw_inactive_message()
            self._readout_var.set("")

    def update_bindings(self, bound_inputs: list[str] | None = None):
        """Update X range when bindings change (assign/unassign)."""
        old_x_min = self._x_min
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

    def _build_pipeline(self):
        """Build a shaping closure from the current action parameters."""
        action = self._action
        if not action or action.input_type != InputType.ANALOG:
            self._pipeline = None
            self._slew = None
            return

        mode = action.trigger_mode
        inversion = action.inversion
        deadband = action.deadband
        scale = action.scale
        extra = action.extra or {}

        # RAW — true passthrough
        if mode == EventTriggerMode.RAW:
            self._pipeline = lambda raw: raw
            self._y_min = -1.0
            self._y_max = 1.0
            self._slew = None
            return

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

        self._pipeline = pipeline
        self._compute_y_range()

        # Slew rate limiter
        slew_rate = action.slew_rate
        if slew_rate > 0:
            neg_rate = extra.get("negative_slew_rate")
            if neg_rate is None:
                neg_rate = -slew_rate
            else:
                neg_rate = float(neg_rate)
            self._slew = SimpleSlewLimiter(
                slew_rate, neg_rate, dt=_TICK_MS / 1000.0)
        else:
            self._slew = None

    _Y_RANGE_SAMPLES = 200

    def _compute_y_range(self):
        """Auto-scale Y axis by sampling pipeline output across x range."""
        if not self._pipeline:
            self._y_min = -1.0
            self._y_max = 1.0
            return
        y_min = 0.0
        y_max = 0.0
        n = self._Y_RANGE_SAMPLES
        x_span = 1.0 - self._x_min
        for i in range(n + 1):
            x = self._x_min + x_span * i / n
            y = self._pipeline(x)
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
        self._draw_motor()

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

    def _draw_trail(self):
        """Draw fading history dots from oldest (dim) to newest (bright)."""
        c = self._canvas
        n = len(self._trail)
        if n == 0:
            return

        for i, (tx, ty) in enumerate(self._trail):
            # Fraction: 0 = oldest, 1 = newest
            frac = i / max(n - 1, 1)
            r = int(_TRAIL_OLDEST[0] + frac * (
                _TRAIL_NEWEST[0] - _TRAIL_OLDEST[0]))
            g = int(_TRAIL_OLDEST[1] + frac * (
                _TRAIL_NEWEST[1] - _TRAIL_OLDEST[1]))
            b = int(_TRAIL_OLDEST[2] + frac * (
                _TRAIL_NEWEST[2] - _TRAIL_OLDEST[2]))
            color = f"#{r:02x}{g:02x}{b:02x}"

            cx, cy = self._d2c(tx, ty)
            radius = 2 + frac * 2  # 2px oldest, 4px newest
            c.create_oval(cx - radius, cy - radius,
                          cx + radius, cy + radius,
                          fill=color, outline="")

    def _draw_current(self):
        """Draw the large dot at current (input, output)."""
        c = self._canvas
        cx, cy = self._d2c(self._last_input, self._last_output)
        c.create_oval(cx - _DOT_RADIUS, cy - _DOT_RADIUS,
                      cx + _DOT_RADIUS, cy + _DOT_RADIUS,
                      fill=_DOT_COLOR, outline=_DOT_OUTLINE, width=1.5)

    def _draw_motor(self):
        """Draw a spinning motor indicator in the bottom-right of the plot."""
        c = self._canvas
        mx = self._margin_x
        my = self._margin_y
        pw = self._plot_w
        ph = self._plot_h

        # Center of motor circle: bottom-right corner, inset by margin
        motor_cx = mx + pw - _MOTOR_RADIUS - _MOTOR_MARGIN
        motor_cy = my + ph - _MOTOR_RADIUS - _MOTOR_MARGIN

        # Outer circle
        c.create_oval(
            motor_cx - _MOTOR_RADIUS, motor_cy - _MOTOR_RADIUS,
            motor_cx + _MOTOR_RADIUS, motor_cy + _MOTOR_RADIUS,
            outline=_MOTOR_OUTLINE, fill=_MOTOR_BG, width=1.5)

        # Rotating dot on the rim
        orbit_r = _MOTOR_RADIUS - _MOTOR_DOT_RADIUS - 2
        dot_x = motor_cx + orbit_r * math.cos(self._motor_angle)
        dot_y = motor_cy + orbit_r * math.sin(self._motor_angle)
        c.create_oval(
            dot_x - _MOTOR_DOT_RADIUS, dot_y - _MOTOR_DOT_RADIUS,
            dot_x + _MOTOR_DOT_RADIUS, dot_y + _MOTOR_DOT_RADIUS,
            fill=_MOTOR_DOT_COLOR, outline="")

    # ------------------------------------------------------------------
    # Slider Callbacks
    # ------------------------------------------------------------------

    def _on_x_slider(self, val):
        """X slider changed — sync Y slider to match."""
        if self._syncing_slider:
            return
        self._syncing_slider = True
        self._y_slider.set(float(val))
        self._syncing_slider = False

    def _on_y_slider(self, val):
        """Y slider changed — sync X slider to match."""
        if self._syncing_slider:
            return
        self._syncing_slider = True
        self._x_slider.set(float(val))
        self._syncing_slider = False

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

        # Read current slider value
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

        # Advance motor angle: output=1 → 2π rad/s
        dt = _TICK_MS / 1000.0
        self._motor_angle += output * _MOTOR_SPEED * dt

        # Append to trail
        self._trail.append((raw_input, output))
        if len(self._trail) > _TRAIL_MAX:
            self._trail.pop(0)

        # Update readout
        self._readout_var.set(
            f"In: {raw_input:+.3f}  \u2192  Out: {output:+.3f}")

        # Redraw
        self._draw()

        # Schedule next tick
        self._tick_id = self.after(_TICK_MS, self._tick)
