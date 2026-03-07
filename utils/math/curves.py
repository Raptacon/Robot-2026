"""Portable curve evaluation functions for spline and piecewise-linear curves.

Pure Python -- no wpilib or GUI dependencies. These functions are the
canonical implementations shared by both the robot code (utils/input/)
and the host GUI tool (host/controller_config/).

Spline evaluation uses cubic hermite interpolation, mathematically
identical to wpimath.spline.CubicHermiteSpline (see spline_editor.py
module docstring for the wpimath construction recipe).

Control point formats (stored in ActionDefinition.extra):

    Spline: [{"x": float, "y": float, "tangent": float}, ...]
    Segment: [{"x": float, "y": float}, ...]
"""


def hermite_eval(y0, m0, y1, m1, dx, t):
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


def default_spline_points() -> list[dict]:
    """Generate default 3-point linear control points (y = x)."""
    return [
        {"x": -1.0, "y": -1.0, "tangent": 1.0},
        {"x": 0.0, "y": 0.0, "tangent": 1.0},
        {"x": 1.0, "y": 1.0, "tangent": 1.0},
    ]


def evaluate_spline(points: list[dict], x: float) -> float:
    """Evaluate the cubic hermite spline at input *x*, returning output *y*.

    Mathematically identical to wpimath.spline.CubicHermiteSpline.
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
            return hermite_eval(
                points[i]["y"], points[i]["tangent"],
                points[i + 1]["y"], points[i + 1]["tangent"],
                dx, t)
    return x


def numerical_slope(points: list[dict], x: float) -> float:
    """Estimate dy/dx at *x* by central difference."""
    eps = 0.001
    return (evaluate_spline(points, x + eps)
            - evaluate_spline(points, x - eps)) / (2 * eps)


def default_segment_points() -> list[dict]:
    """Generate default 3-point linear control points (y = x)."""
    return [
        {"x": -1.0, "y": -1.0},
        {"x": 0.0, "y": 0.0},
        {"x": 1.0, "y": 1.0},
    ]


def evaluate_segments(points: list[dict], x: float) -> float:
    """Evaluate the piecewise-linear curve at input *x*.

    Linearly interpolates between adjacent control points.
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
            y0, y1 = points[i]["y"], points[i + 1]["y"]
            return y0 + t * (y1 - y0)
    return x
