"""Segment editor dialog for analog piecewise-linear response curves.

Visual piecewise-linear editor that maps joystick input (X: -1 to 1)
to output (Y: -1 to 1). Users can add, remove, and drag control points
to shape the response curve. Values between points are linearly
interpolated, allowing different slopes in different regions.

Control point data format (stored in ActionDefinition.extra)::

    action.extra["segment_points"] = [
        {"x": -1.0, "y": -1.0},
        {"x":  0.0, "y":  0.0},
        {"x":  1.0, "y":  1.0},
    ]

Endpoints (x=-1 and x=1) are always present; intermediate points
can be added or removed freely.
"""

import math
import tkinter as tk
from copy import deepcopy
from tkinter import ttk, filedialog, messagebox

import yaml

from host.controller_config.colors import (
    BG_WHITE,
    CURVE_LINE,
    ENDPOINT_FILL,
    POINT_FILL,
    POINT_OUTLINE,
)
from host.controller_config.editor_utils import (
    DIALOG_H,
    DIALOG_MARGIN,
    DIALOG_PLOT_H,
    DIALOG_PLOT_W,
    DIALOG_W,
    UndoStack,
    draw_editor_grid,
)

# Visual sizes (pixels)
_POINT_RADIUS = 7

# Minimum gap between adjacent control point X positions
_MIN_X_GAP = 0.04

_DEFAULT_STATUS = ("Click to add point | Right-click to remove | "
                   "Drag to adjust")


# ---------------------------------------------------------------------------
#   Piecewise-linear evaluation (canonical in utils/math/curves.py)
# ---------------------------------------------------------------------------

from utils.math.curves import default_segment_points


# ---------------------------------------------------------------------------
#   SegmentEditorDialog
# ---------------------------------------------------------------------------

class SegmentEditorDialog(tk.Toplevel):
    """Modal dialog for visually editing a piecewise-linear response curve.

    Interactions:
      - Left-click on empty space: add a new control point
      - Right-click on a point: remove it (not endpoints)
      - Drag a control point: move Y (endpoints) or X+Y (intermediate)

    Options:
      - Symmetry: odd symmetry — edit positive side, negative mirrors
      - Monotonic: Y values must increase left-to-right (enabled by default)
    """

    def __init__(self, parent, points: list[dict],
                 other_curves: dict[str, list[dict]] | None = None):
        """
        Args:
            parent: parent window
            points: initial control points
            other_curves: optional {action_name: points} for "Copy from..."
        """
        super().__init__(parent)
        self.title("Segmented Response Curve Editor")
        self.transient(parent)
        self.resizable(False, False)

        self._points = [dict(p) for p in points]
        self._points.sort(key=lambda p: p["x"])
        self._result = None
        self._symmetric = False
        self._monotonic = True
        self._other_curves = other_curves or {}

        # Drag state
        self._drag_idx = None

        # Undo stack (max 30 snapshots)
        self._undo = UndoStack()
        self._drag_undo_pushed = False

        self._build_ui()
        self._draw()

        # Center on the parent window
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
    # Undo
    # ------------------------------------------------------------------

    def _push_undo(self):
        """Save current points to undo stack."""
        self._undo.push(self._points)

    def _pop_undo(self):
        """Restore previous points from undo stack."""
        state = self._undo.pop()
        if state is None:
            self._status_var.set("Nothing to undo")
            return
        self._points = state
        self._draw()
        self._status_var.set(f"Undo ({len(self._undo)} remaining)")

    # ------------------------------------------------------------------
    # Import / Export / Copy
    # ------------------------------------------------------------------

    def _on_export(self):
        """Export current curve points to a YAML file."""
        path = filedialog.asksaveasfilename(
            parent=self, title="Export Segment Curve",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")])
        if not path:
            return
        data = {"type": "segment", "points": deepcopy(self._points)}
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        self._status_var.set(f"Exported to {path}")

    def _on_import(self):
        """Import curve points from a YAML file."""
        path = filedialog.askopenfilename(
            parent=self, title="Import Segment Curve",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as exc:
            messagebox.showerror("Import Failed",
                                 f"Could not read YAML file:\n{exc}",
                                 parent=self)
            return

        if isinstance(data, dict):
            points = data.get("points", [])
        elif isinstance(data, list):
            points = data
        else:
            messagebox.showerror(
                "Import Failed",
                "File does not contain curve data.\n"
                "Expected a 'points' list of {{x, y}} entries.",
                parent=self)
            return

        if not points:
            messagebox.showerror(
                "Import Failed",
                "No points found in file.\n"
                "Expected a 'points' key containing a list.",
                parent=self)
            return

        if not isinstance(points, list) or not all(
                isinstance(p, dict) and "x" in p and "y" in p
                for p in points):
            messagebox.showerror(
                "Import Failed",
                "Invalid point data. Each point must have "
                "'x' and 'y' fields.",
                parent=self)
            return

        self._push_undo()
        # Strip tangent field — segment points don't use it
        self._points = [{"x": p["x"], "y": p["y"]} for p in points]
        self._points.sort(key=lambda p: p["x"])
        self._draw()
        self._status_var.set(f"Imported from {path}")

    def _on_copy_from(self):
        """Copy curve data from another action."""
        if not self._other_curves:
            return
        win = tk.Toplevel(self)
        win.title("Copy Curve From...")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        ttk.Label(win, text="Select an action to copy its curve:",
                  padding=5).pack(anchor=tk.W)
        listbox = tk.Listbox(win, height=min(10, len(self._other_curves)),
                             width=40)
        listbox.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        names = sorted(self._other_curves.keys())
        for name in names:
            listbox.insert(tk.END, name)

        def on_ok():
            sel = listbox.curselection()
            if not sel:
                return
            chosen = names[sel[0]]
            pts = self._other_curves[chosen]
            self._push_undo()
            self._points = [{"x": p["x"], "y": p["y"]} for p in pts]
            self._points.sort(key=lambda p: p["x"])
            self._draw()
            self._status_var.set(f"Copied curve from {chosen}")
            win.destroy()

        listbox.bind("<Double-1>", lambda e: on_ok())
        bf = ttk.Frame(win)
        bf.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(bf, text="OK", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bf, text="Cancel",
                   command=win.destroy).pack(side=tk.RIGHT)

        # Center on parent editor dialog
        win.update_idletasks()
        px, py = self.winfo_rootx(), self.winfo_rooty()
        pw, ph = self.winfo_width(), self.winfo_height()
        ww, wh = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - ww) // 2}+{py + (ph - wh) // 2}")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._canvas = tk.Canvas(
            self, width=DIALOG_W, height=DIALOG_H,
            bg=BG_WHITE, cursor="crosshair")
        self._canvas.pack(padx=10, pady=(10, 5))

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", self._on_right_click)

        self._status_var = tk.StringVar(value=_DEFAULT_STATUS)
        ttk.Label(self, textvariable=self._status_var,
                  relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, padx=10)

        # Top button row: file and copy operations
        top_btn = ttk.Frame(self)
        top_btn.pack(fill=tk.X, padx=10, pady=(5, 0))
        ttk.Button(top_btn, text="Export YAML",
                   command=self._on_export).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_btn, text="Import YAML",
                   command=self._on_import).pack(side=tk.LEFT, padx=5)
        if self._other_curves:
            ttk.Button(top_btn, text="Copy from...",
                       command=self._on_copy_from).pack(side=tk.LEFT, padx=5)

        # Bottom button row: edit operations
        btn = ttk.Frame(self)
        btn.pack(fill=tk.X, padx=10, pady=(5, 10))
        ttk.Button(btn, text="Reset to Linear",
                   command=self._on_reset).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="Undo",
                   command=self._pop_undo).pack(side=tk.LEFT, padx=5)
        self._sym_var = tk.BooleanVar()
        ttk.Checkbutton(btn, text="Symmetry", variable=self._sym_var,
                        command=self._on_symmetry_toggle
                        ).pack(side=tk.LEFT, padx=5)
        self._mono_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn, text="Monotonic", variable=self._mono_var,
                        command=self._on_monotonic_toggle
                        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="Cancel",
                   command=self._on_cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn, text="OK",
                   command=self._on_ok).pack(side=tk.RIGHT, padx=5)

        self.bind("<Control-z>", lambda e: self._pop_undo())

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def _d2c(self, x: float, y: float) -> tuple[float, float]:
        """Data (-1..1) to canvas pixels."""
        cx = DIALOG_MARGIN + (x + 1) / 2 * DIALOG_PLOT_W
        cy = DIALOG_MARGIN + (1 - y) / 2 * DIALOG_PLOT_H
        return cx, cy

    def _c2d(self, cx: float, cy: float) -> tuple[float, float]:
        """Canvas pixels to data (-1..1)."""
        x = (cx - DIALOG_MARGIN) / DIALOG_PLOT_W * 2 - 1
        y = 1 - (cy - DIALOG_MARGIN) / DIALOG_PLOT_H * 2
        return x, y

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self):
        c = self._canvas
        c.delete("all")
        self._draw_grid()
        self._draw_curve()
        self._draw_points()

    def _draw_grid(self):
        draw_editor_grid(self._canvas, self._d2c,
                         DIALOG_MARGIN, DIALOG_PLOT_W, DIALOG_PLOT_H,
                         DIALOG_W, DIALOG_H)

    def _draw_curve(self):
        pts = self._points
        if len(pts) < 2:
            return
        coords = []
        for pt in pts:
            cx, cy = self._d2c(pt["x"], pt["y"])
            coords.extend([cx, cy])
        if len(coords) >= 4:
            self._canvas.create_line(
                *coords, fill=CURVE_LINE, width=2, smooth=False)

    def _draw_points(self):
        c = self._canvas
        for i, pt in enumerate(self._points):
            cx, cy = self._d2c(pt["x"], pt["y"])
            is_endpoint = (i == 0 or i == len(self._points) - 1)
            is_mirror = (self._symmetric
                         and pt["x"] < -_MIN_X_GAP / 2)
            if is_mirror:
                fill = "#c0a0a0"
            elif is_endpoint:
                fill = ENDPOINT_FILL
            else:
                fill = POINT_FILL
            c.create_oval(cx - _POINT_RADIUS, cy - _POINT_RADIUS,
                          cx + _POINT_RADIUS, cy + _POINT_RADIUS,
                          fill=fill, outline=POINT_OUTLINE, width=2)

    # ------------------------------------------------------------------
    # Hit testing & interaction
    # ------------------------------------------------------------------

    def _hit_test(self, cx, cy):
        """Find what point is at canvas position (cx, cy).

        Returns index or None.
        When symmetry is on, negative-side mirrors are not interactive.
        """
        for i, pt in enumerate(self._points):
            if self._symmetric and pt["x"] < -_MIN_X_GAP / 2:
                continue
            px, py = self._d2c(pt["x"], pt["y"])
            if math.hypot(cx - px, cy - py) <= _POINT_RADIUS + 3:
                return i
        return None

    def _is_endpoint(self, idx: int) -> bool:
        return idx == 0 or idx == len(self._points) - 1

    def _add_point_at(self, cx, cy):
        """Add a new control point at canvas position."""
        x, y = self._c2d(cx, cy)

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

        if self._monotonic:
            y = self._clamp_monotonic_insert(x, y)

        self._push_undo()
        self._points.append({
            "x": round(x, 3),
            "y": round(y, 3),
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
        self._push_undo()
        self._points.pop(idx)
        if self._symmetric:
            self._enforce_symmetry()
        self._draw()
        self._status_var.set(
            f"Removed point ({len(self._points)} points)")

    def _on_press(self, event):
        hit = self._hit_test(event.x, event.y)
        if hit is not None:
            self._drag_idx = hit
            self._drag_undo_pushed = False
        else:
            self._drag_idx = None
            self._add_point_at(event.x, event.y)

    def _on_drag(self, event):
        if self._drag_idx is None:
            return
        if not self._drag_undo_pushed:
            self._push_undo()
            self._drag_undo_pushed = True
        i = self._drag_idx
        pt = self._points[i]

        _, y = self._c2d(event.x, event.y)
        if self._symmetric and abs(pt["x"]) < _MIN_X_GAP / 2:
            pt["y"] = 0.0
        else:
            y = max(-1.0, min(1.0, y))
            if self._monotonic:
                y = self._clamp_monotonic(i, y)
            pt["y"] = round(y, 3)

        if not self._is_endpoint(i):
            x, _ = self._c2d(event.x, event.y)
            x_lo = self._points[i - 1]["x"] + _MIN_X_GAP
            x_hi = self._points[i + 1]["x"] - _MIN_X_GAP
            if self._symmetric and pt["x"] > 0:
                x_lo = max(x_lo, _MIN_X_GAP)
            pt["x"] = round(max(x_lo, min(x_hi, x)), 3)

            # Re-enforce monotonic after X move changes neighbors
            if self._monotonic:
                y_clamped = self._clamp_monotonic(i, pt["y"])
                pt["y"] = round(y_clamped, 3)

        if self._symmetric:
            self._enforce_symmetry()
            for j, p in enumerate(self._points):
                if p is pt:
                    self._drag_idx = j
                    break

        self._status_var.set(
            f"Point {self._drag_idx}: x={pt['x']:.2f}  y={pt['y']:.3f}")
        self._draw()

    def _on_release(self, event):
        self._drag_idx = None
        self._status_var.set(_DEFAULT_STATUS)

    def _on_right_click(self, event):
        """Remove a control point on right-click."""
        hit = self._hit_test(event.x, event.y)
        if hit is None:
            return
        if self._is_endpoint(hit):
            self._status_var.set("Cannot remove endpoints")
            return
        if len(self._points) <= 2:
            self._status_var.set("Need at least 2 points")
            return
        self._drag_idx = None
        self._remove_point(hit)

    # ------------------------------------------------------------------
    # Monotonic constraint
    # ------------------------------------------------------------------

    def _clamp_monotonic(self, idx: int, y: float) -> float:
        """Clamp *y* so the curve stays monotonically increasing."""
        if idx > 0:
            y = max(y, self._points[idx - 1]["y"])
        if idx < len(self._points) - 1:
            y = min(y, self._points[idx + 1]["y"])
        return y

    def _clamp_monotonic_insert(self, x: float, y: float) -> float:
        """Clamp *y* for a new point at *x* to maintain monotonicity."""
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
        """Fix all points to be monotonically increasing in Y."""
        for i in range(1, len(self._points)):
            if self._points[i]["y"] < self._points[i - 1]["y"]:
                self._points[i]["y"] = self._points[i - 1]["y"]

    # ------------------------------------------------------------------
    # Symmetry
    # ------------------------------------------------------------------

    def _on_symmetry_toggle(self):
        """Handle the Symmetry checkbox toggle."""
        self._push_undo()
        self._symmetric = self._sym_var.get()
        if self._symmetric:
            self._enforce_symmetry()
            self._draw()
            self._status_var.set("Symmetry on — edit positive side")

    def _enforce_symmetry(self):
        """Rebuild negative-side points as odd mirrors of positive side."""
        positive = [pt for pt in self._points
                    if pt["x"] > _MIN_X_GAP / 2]
        center = None
        for pt in self._points:
            if abs(pt["x"]) < _MIN_X_GAP / 2:
                center = pt
                break

        if center is None:
            center = {"x": 0.0, "y": 0.0}
        else:
            center["x"] = 0.0
            center["y"] = 0.0

        new_points = []
        for pt in reversed(positive):
            new_points.append({
                "x": round(-pt["x"], 3),
                "y": round(-pt["y"], 3),
            })
        new_points.append(center)
        new_points.extend(positive)
        self._points = new_points

    # ------------------------------------------------------------------
    # Monotonic toggle
    # ------------------------------------------------------------------

    def _on_monotonic_toggle(self):
        """Handle the Monotonic checkbox toggle."""
        self._push_undo()
        self._monotonic = self._mono_var.get()
        if self._monotonic:
            self._enforce_monotonic()
            self._draw()
            self._status_var.set(
                "Monotonic on — output increases with input")

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def _on_reset(self):
        self._push_undo()
        self._points = default_segment_points()
        if self._symmetric:
            self._enforce_symmetry()
        if self._monotonic:
            self._enforce_monotonic()
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
