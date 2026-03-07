"""Portable math utilities shared between robot code and host tools."""

from .curves import (
    default_segment_points,
    default_spline_points,
    evaluate_segments,
    evaluate_spline,
    hermite_eval,
    numerical_slope,
)

__all__ = [
    "default_segment_points",
    "default_spline_points",
    "evaluate_segments",
    "evaluate_spline",
    "hermite_eval",
    "numerical_slope",
]
