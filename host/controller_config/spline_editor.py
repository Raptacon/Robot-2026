"""Spline editor dialog for analog action response curves.

Visual cubic hermite spline editor that maps joystick input (X: -1 to 1)
to output (Y: -1 to 1). Users can add, remove, and drag control points
to shape the response curve.

The evaluation uses standard cubic hermite interpolation, mathematically
identical to wpimath.spline.CubicHermiteSpline. For robot-side evaluation,
construct each segment between adjacent control points as::

    from wpimath.spline import CubicHermiteSpline

    dx = x1 - x0
    spline = CubicHermiteSpline(
        (x0, dx), (x1, dx),           # x control vectors (linear in x)
        (y0, m0 * dx), (y1, m1 * dx)  # y control vectors (shaped output)
    )
    pose, curvature = spline.getPoint(t)  # t = (x - x0) / dx
    output = pose.y                        # the mapped output value

Control point data format (stored in ActionDefinition.extra)::

    action.extra["spline_points"] = [
        {"x": -1.0, "y": -1.0, "tangent": 1.0},
        {"x":  0.0, "y":  0.0, "tangent": 1.0},
        {"x":  1.0, "y":  1.0, "tangent": 1.0},
    ]

Endpoints (x=-1 and x=1) are always present; intermediate points
can be added or removed freely.
"""

import math
import tkinter as tk
from tkinter import ttk

# Canvas layout (pixels)
_CANVAS_W = 500
_CANVAS_H = 500
_MARGIN = 50
_PLOT_W = _CANVAS_W - 2 * _MARGIN
_PLOT_H = _CANVAS_H - 2 * _MARGIN

# Visual sizes (pixels)
_POINT_RADIUS = 7
_HANDLE_RADIUS = 5
_HANDLE_LENGTH = 50
_CURVE_SAMPLES_PER_SEG = 80

# Minimum gap between adjacent control point X positions
_MIN_X_GAP = 0.04

# Colors
_BG = "#ffffff"
_GRID = "#e8e8e8"
_GRID_MAJOR = "#c8c8c8"
_AXIS = "#909090"
_CURVE = "#2060c0"
_POINT_FILL = "#c02020"
_POINT_OUTLINE = "#801010"
_ENDPOINT_FILL = "#802020"
_HANDLE_FILL = "#40a040"
_HANDLE_LINE = "#80c080"
_LABEL = "#505050"

_DEFAULT_STATUS = ("Click to add point | Right-click to remove | "
                   "Drag to adjust")


# ------------------------------------------------------------------
# Spline math
# ------------------------------------------------------------------

def _hermite_eval(y0, m0, y1, m1, dx, t):
    """Evaluate one cubic hermite segment at parameter *t* in [0, 1].

    Args:
        y0, y1: endpoint Y values
        m0, m1: endpoint slopes (dy/dx)
        dx: segment width (x1 - x0)
        t: parameter in [0, 1]
    """
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return h00 * y0 + h10 * dx * m0 + h01 * y1 + h11 * dx * m1


def default_points() -> list[dict]:
    """Generate default 3-point linear control points (y = x)."""
    return [
        {"x": -1.0, "y": -1.0, "tangent": 1.0},
        {"x": 0.0, "y": 0.0, "tangent": 1.0},
        {"x": 1.0, "y": 1.0, "tangent": 1.0},
    ]


def evaluate_spline(points: list[dict], x: float) -> float:
    """Evaluate the cubic hermite spline at input *x*, returning output *y*.

    Mathematically identical to wpimath.spline.CubicHermiteSpline
    (see module docstring for the wpimath construction recipe).
    """
    if not points or len(points) < 2:
        return x
    x = max(points[0]["x"], min(points[-1]["x"], x))
    for i in range(len(points) - 1):
        x0, x1 = points[i]["x"], points[i + 1]["x"]
        if x <= x1 or i == len(points) - 2:
            dx = x1 - x0
            if dx == 0:
                return points[i]["y"]
            t = (x - x0) / dx
            return _hermite_eval(
                points[i]["y"], points[i]["tangent"],
                points[i + 1]["y"], points[i + 1]["tangent"],
                dx, t)
    return x


def _numerical_slope(points: list[dict], x: float) -> float:
    """Estimate dy/dx at *x* by central difference."""
    eps = 0.001
    return (evaluate_spline(points, x + eps)
            - evaluate_spline(points, x - eps)) / (2 * eps)


# ------------------------------------------------------------------
# SplineEditorDialog
# ------------------------------------------------------------------

class SplineEditorDialog(tk.Toplevel):
    """Modal dialog for visually editing a cubic hermite spline curve.

    Interactions:
      - Left-click on empty space: add a new control point
      - Right-click on a point: remove it (not endpoints)
      - Drag a red control point: move Y (endpoints) or X+Y (intermediate)
      - Drag a green tangent handle: adjust slope at that point
    """

    def __init__(self, parent, points: list[dict]):
        super().__init__(parent)
        self.title("Spline Response Curve Editor")
        self.transient(parent)
        self.resizable(False, False)

        self._points = [dict(p) for p in points]
        self._points.sort(key=lambda p: p["x"])
        self._result = None
        self._symmetric = False

        # Drag state
        self._drag_type = None   # "point" or "handle"
        self._drag_idx = None
        self._drag_side = None   # "in" or "out"

        self._build_ui()
        self._draw()

        # Center on the parent window (follows it across monitors)
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        dw = self.winfo_reqwidth()
        dh = self.winfo_reqheight()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        self.geometry(f"+{x}+{y}")

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.focus_set()

    def get_result(self) -> list[dict] | None:
        """Block until dialog closes. Returns points list or None."""
        self.wait_window()
        return self._result

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._canvas = tk.Canvas(
            self, width=_CANVAS_W, height=_CANVAS_H,
            bg=_BG, cursor="crosshair")
        self._canvas.pack(padx=10, pady=(10, 5))

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", self._on_right_click)

        self._status_var = tk.StringVar(value=_DEFAULT_STATUS)
        ttk.Label(self, textvariable=self._status_var,
                  relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, padx=10)

        btn = ttk.Frame(self)
        btn.pack(fill=tk.X, padx=10, pady=(5, 10))
        ttk.Button(btn, text="Reset to Linear",
                   command=self._on_reset).pack(side=tk.LEFT, padx=5)
        self._sym_var = tk.BooleanVar()
        ttk.Checkbutton(btn, text="Symmetry", variable=self._sym_var,
                        command=self._on_symmetry_toggle
                        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="Cancel",
                   command=self._on_cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn, text="OK",
                   command=self._on_ok).pack(side=tk.RIGHT, padx=5)

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def _d2c(self, x: float, y: float) -> tuple[float, float]:
        """Data (-1..1) to canvas pixels."""
        cx = _MARGIN + (x + 1) / 2 * _PLOT_W
        cy = _MARGIN + (1 - y) / 2 * _PLOT_H
        return cx, cy

    def _c2d(self, cx: float, cy: float) -> tuple[float, float]:
        """Canvas pixels to data (-1..1)."""
        x = (cx - _MARGIN) / _PLOT_W * 2 - 1
        y = 1 - (cy - _MARGIN) / _PLOT_H * 2
        return x, y

    def _tangent_offset(self, tangent: float) -> tuple[float, float]:
        """Tangent slope to canvas-pixel offset for handle drawing."""
        ppx = _PLOT_W / 2   # pixels per data unit, X
        ppy = _PLOT_H / 2   # pixels per data unit, Y
        dx = 1.0 * ppx
        dy = -tangent * ppy  # canvas Y inverted
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return float(_HANDLE_LENGTH), 0.0
        s = _HANDLE_LENGTH / length
        return dx * s, dy * s

    def _offset_to_tangent(self, dx: float, dy: float) -> float:
        """Canvas-pixel offset back to tangent slope."""
        ppx = _PLOT_W / 2
        ppy = _PLOT_H / 2
        data_dx = dx / ppx
        data_dy = -dy / ppy
        if abs(data_dx) < 1e-6:
            return 10.0 if data_dy > 0 else -10.0
        return data_dy / data_dx

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self):
        c = self._canvas
        c.delete("all")
        self._draw_grid()
        self._draw_curve()
        self._draw_handles()
        self._draw_points()

    def _draw_grid(self):
        c = self._canvas
        for v in [i / 4 for i in range(-4, 5)]:
            cx, _ = self._d2c(v, 0)
            _, cy = self._d2c(0, v)
            is_axis = abs(v) < 0.01
            is_major = abs(v * 2) % 1 < 0.01
            color = _AXIS if is_axis else (_GRID_MAJOR if is_major else _GRID)
            w = 2 if is_axis else 1
            c.create_line(cx, _MARGIN, cx, _MARGIN + _PLOT_H,
                          fill=color, width=w)
            c.create_line(_MARGIN, cy, _MARGIN + _PLOT_W, cy,
                          fill=color, width=w)

        for v in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            cx, _ = self._d2c(v, 0)
            c.create_text(cx, _MARGIN + _PLOT_H + 15,
                          text=f"{v:g}", fill=_LABEL,
                          font=("TkDefaultFont", 8))
            _, cy = self._d2c(0, v)
            c.create_text(_MARGIN - 22, cy,
                          text=f"{v:g}", fill=_LABEL,
                          font=("TkDefaultFont", 8))

        c.create_text(_CANVAS_W / 2, _CANVAS_H - 5,
                      text="Input", fill=_LABEL,
                      font=("TkDefaultFont", 9))
        c.create_text(12, _CANVAS_H / 2, text="Output",
                      fill=_LABEL, font=("TkDefaultFont", 9), angle=90)
        c.create_rectangle(_MARGIN, _MARGIN,
                           _MARGIN + _PLOT_W, _MARGIN + _PLOT_H,
                           outline="#808080")

    def _draw_curve(self):
        pts = self._points
        if len(pts) < 2:
            return
        n = _CURVE_SAMPLES_PER_SEG * (len(pts) - 1)
        x_min, x_max = pts[0]["x"], pts[-1]["x"]
        coords = []
        for i in range(n + 1):
            x = x_min + (x_max - x_min) * i / n
            y = max(-1.5, min(1.5, evaluate_spline(pts, x)))
            cx, cy = self._d2c(x, y)
            coords.extend([cx, cy])
        if len(coords) >= 4:
            self._canvas.create_line(
                *coords, fill=_CURVE, width=2, smooth=False)

    def _draw_handles(self):
        c = self._canvas
        for i, pt in enumerate(self._points):
            cx, cy = self._d2c(pt["x"], pt["y"])
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

    def _draw_points(self):
        c = self._canvas
        for i, pt in enumerate(self._points):
            cx, cy = self._d2c(pt["x"], pt["y"])
            is_endpoint = (i == 0 or i == len(self._points) - 1)
            is_mirror = (self._symmetric
                         and pt["x"] < -_MIN_X_GAP / 2)
            if is_mirror:
                fill = "#c0a0a0"   # muted — auto-mirrored, not draggable
            elif is_endpoint:
                fill = _ENDPOINT_FILL
            else:
                fill = _POINT_FILL
            c.create_oval(cx - _POINT_RADIUS, cy - _POINT_RADIUS,
                          cx + _POINT_RADIUS, cy + _POINT_RADIUS,
                          fill=fill, outline=_POINT_OUTLINE, width=2)

    # ------------------------------------------------------------------
    # Hit testing & interaction
    # ------------------------------------------------------------------

    def _hit_test(self, cx, cy):
        """Find what element is at canvas position (cx, cy).

        Returns (type, index, side) or None.
        When symmetry is on, negative-side mirrors are not interactive.
        """
        # Check handles first (smaller targets, higher priority)
        for i, pt in enumerate(self._points):
            if self._symmetric and pt["x"] < -_MIN_X_GAP / 2:
                continue
            px, py = self._d2c(pt["x"], pt["y"])
            hdx, hdy = self._tangent_offset(pt["tangent"])
            if i < len(self._points) - 1:
                if math.hypot(cx - (px + hdx),
                              cy - (py + hdy)) <= _HANDLE_RADIUS + 3:
                    return ("handle", i, "out")
            if i > 0:
                if math.hypot(cx - (px - hdx),
                              cy - (py - hdy)) <= _HANDLE_RADIUS + 3:
                    return ("handle", i, "in")
        # Then check points
        for i, pt in enumerate(self._points):
            if self._symmetric and pt["x"] < -_MIN_X_GAP / 2:
                continue
            px, py = self._d2c(pt["x"], pt["y"])
            if math.hypot(cx - px, cy - py) <= _POINT_RADIUS + 3:
                return ("point", i, None)
        return None

    def _is_endpoint(self, idx: int) -> bool:
        """True if point at *idx* is the first or last point."""
        return idx == 0 or idx == len(self._points) - 1

    def _add_point_at(self, cx, cy):
        """Add a new control point at canvas position."""
        x, y = self._c2d(cx, cy)

        # When symmetric, only allow adding on the positive side
        if self._symmetric and x < -_MIN_X_GAP / 2:
            self._status_var.set(
                "Add points on the positive side (symmetry)")
            return

        x_min = self._points[0]["x"]
        x_max = self._points[-1]["x"]
        if x <= x_min + _MIN_X_GAP or x >= x_max - _MIN_X_GAP:
            return
        y = max(-1.0, min(1.0, y))

        # Don't add if too close to an existing point
        for pt in self._points:
            if abs(pt["x"] - x) < _MIN_X_GAP:
                return

        tangent = _numerical_slope(self._points, x)
        self._points.append({
            "x": round(x, 3),
            "y": round(y, 3),
            "tangent": round(tangent, 3),
        })
        self._points.sort(key=lambda p: p["x"])

        if self._symmetric:
            self._enforce_symmetry()

        self._draw()
        self._status_var.set(
            f"Added point at x={x:.2f} ({len(self._points)} points)")

    def _remove_point(self, idx):
        """Remove the control point at *idx* (not endpoints)."""
        if self._is_endpoint(idx) or len(self._points) <= 2:
            return
        self._points.pop(idx)
        if self._symmetric:
            self._enforce_symmetry()
        self._draw()
        self._status_var.set(
            f"Removed point ({len(self._points)} points)")

    def _on_press(self, event):
        hit = self._hit_test(event.x, event.y)
        if hit:
            self._drag_type, self._drag_idx, self._drag_side = hit
        else:
            self._drag_type = None
            self._add_point_at(event.x, event.y)

    def _on_drag(self, event):
        if self._drag_type is None:
            return
        i = self._drag_idx
        pt = self._points[i]

        if self._drag_type == "point":
            _, y = self._c2d(event.x, event.y)
            # Center point with symmetry: y locked to 0
            if self._symmetric and abs(pt["x"]) < _MIN_X_GAP / 2:
                pt["y"] = 0.0
            else:
                pt["y"] = round(max(-1.0, min(1.0, y)), 3)
            # Intermediate points: also move X
            if not self._is_endpoint(i):
                x, _ = self._c2d(event.x, event.y)
                x_lo = self._points[i - 1]["x"] + _MIN_X_GAP
                x_hi = self._points[i + 1]["x"] - _MIN_X_GAP
                # With symmetry, keep positive points on positive side
                if self._symmetric and pt["x"] > 0:
                    x_lo = max(x_lo, _MIN_X_GAP)
                pt["x"] = round(max(x_lo, min(x_hi, x)), 3)
        elif self._drag_type == "handle":
            cx, cy = self._d2c(pt["x"], pt["y"])
            dx, dy = event.x - cx, event.y - cy
            if self._drag_side == "in":
                dx, dy = -dx, -dy
            if math.hypot(dx, dy) > 5:
                t = self._offset_to_tangent(dx, dy)
                pt["tangent"] = round(max(-10.0, min(10.0, t)), 3)

        if self._symmetric:
            self._enforce_symmetry()
            # Re-find drag index (positive points keep identity)
            for j, p in enumerate(self._points):
                if p is pt:
                    self._drag_idx = j
                    break

        self._status_var.set(
            f"Point {self._drag_idx}: x={pt['x']:.2f}  y={pt['y']:.3f}  "
            f"tangent={pt['tangent']:.3f}")
        self._draw()

    def _on_release(self, event):
        self._drag_type = None
        self._status_var.set(_DEFAULT_STATUS)

    def _on_right_click(self, event):
        """Remove a control point on right-click."""
        hit = self._hit_test(event.x, event.y)
        if not hit or hit[0] != "point":
            return
        i = hit[1]
        if self._is_endpoint(i):
            self._status_var.set("Cannot remove endpoints")
            return
        if len(self._points) <= 2:
            self._status_var.set("Need at least 2 points")
            return
        # Clear any in-progress drag to avoid stale index
        self._drag_type = None
        self._remove_point(i)

    # ------------------------------------------------------------------
    # Symmetry
    # ------------------------------------------------------------------

    def _on_symmetry_toggle(self):
        """Handle the Symmetry checkbox toggle."""
        self._symmetric = self._sym_var.get()
        if self._symmetric:
            self._enforce_symmetry()
            self._draw()
            self._status_var.set("Symmetry on — edit positive side")

    def _enforce_symmetry(self):
        """Rebuild negative-side points as odd mirrors of positive side.

        Positive-side points (x > 0) are the source of truth.
        Center point (x ~ 0) gets y locked to 0.
        Negative-side points are recreated as mirrors.
        Positive and center dict objects keep their identity so
        in-progress drag indices can be recovered.
        """
        positive = [pt for pt in self._points
                    if pt["x"] > _MIN_X_GAP / 2]
        center = None
        for pt in self._points:
            if abs(pt["x"]) < _MIN_X_GAP / 2:
                center = pt
                break

        if center is None:
            center = {"x": 0.0, "y": 0.0, "tangent": 1.0}
        else:
            center["x"] = 0.0
            center["y"] = 0.0

        new_points = []
        for pt in reversed(positive):
            new_points.append({
                "x": round(-pt["x"], 3),
                "y": round(-pt["y"], 3),
                "tangent": pt["tangent"],
            })
        new_points.append(center)
        new_points.extend(positive)
        self._points = new_points

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def _on_reset(self):
        self._points = default_points()
        if self._symmetric:
            self._enforce_symmetry()
        self._draw()
        self._status_var.set("Reset to linear (3 points)")

    def _on_ok(self):
        self._result = self._points
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self._result = None
        self.grab_release()
        self.destroy()
