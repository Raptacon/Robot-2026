"""Analog input shaping pipeline.

Composes inversion, deadband, response curves, and scaling into a
single callable.  Pipeline order:

    inversion -> deadband -> curve -> scale

The pipeline is built once per action (or rebuilt when a property
changes at runtime) and called every cycle with the raw axis value.
"""

import math
from typing import Callable

from utils.math.curves import evaluate_segments, evaluate_spline
from utils.controller.model import EventTriggerMode


def apply_deadband(value: float, deadband: float) -> float:
    """Apply deadband to a value, linearly rescaling the remaining range.

    Delegates to wpimath when available, falls back to pure-python.
    """
    try:
        from wpimath import applyDeadband
        return applyDeadband(value, deadband)
    except ImportError:
        if abs(value) < deadband:
            return 0.0
        if value > 0:
            return (value - deadband) / (1.0 - deadband)
        return (value + deadband) / (1.0 - deadband)


def curve_squared(value: float) -> float:
    """Squared response curve preserving sign."""
    return math.copysign(value * value, value)


def build_shaping_pipeline(
    inversion: bool,
    deadband: float,
    trigger_mode: EventTriggerMode,
    scale: float,
    extra: dict,
) -> Callable[[float], float]:
    """Compose a full analog shaping pipeline into a single closure.

    Args:
        inversion: If True, negate the raw input before processing.
        deadband: Deadband threshold (0.0 to disable).
        trigger_mode: Determines the response curve applied.
        scale: Output multiplier applied after the curve.
        extra: ActionDefinition.extra dict containing spline_points
               and/or segment_points for SPLINE/SEGMENTED modes.

    Returns:
        A callable ``(float) -> float`` that transforms raw input.

    Pipeline stages by EventTriggerMode:
        RAW:       inversion -> deadband -> scale
        SCALED:    inversion -> deadband -> scale
        SQUARED:   inversion -> deadband -> squared -> scale
        SPLINE:    inversion -> deadband -> spline -> scale
        SEGMENTED: inversion -> deadband -> segments -> scale
    """
    # Pre-resolve curve data so closures don't re-lookup each cycle
    spline_pts = extra.get("spline_points") if extra else None
    segment_pts = extra.get("segment_points") if extra else None

    if trigger_mode == EventTriggerMode.SQUARED:
        def _pipeline(raw: float) -> float:
            v = -raw if inversion else raw
            v = apply_deadband(v, deadband) if deadband > 0 else v
            v = curve_squared(v)
            return v * scale
        return _pipeline

    elif trigger_mode == EventTriggerMode.SPLINE and spline_pts:
        def _pipeline(raw: float) -> float:
            v = -raw if inversion else raw
            v = apply_deadband(v, deadband) if deadband > 0 else v
            v = evaluate_spline(spline_pts, v)
            return v * scale
        return _pipeline

    elif trigger_mode == EventTriggerMode.SEGMENTED and segment_pts:
        def _pipeline(raw: float) -> float:
            v = -raw if inversion else raw
            v = apply_deadband(v, deadband) if deadband > 0 else v
            v = evaluate_segments(segment_pts, v)
            return v * scale
        return _pipeline

    elif trigger_mode == EventTriggerMode.SCALED:
        def _pipeline(raw: float) -> float:
            v = -raw if inversion else raw
            v = apply_deadband(v, deadband) if deadband > 0 else v
            return v * scale
        return _pipeline

    else:
        # RAW or unrecognized — passthrough with optional
        # inversion, deadband, and scale
        def _pipeline(raw: float) -> float:
            v = -raw if inversion else raw
            v = apply_deadband(v, deadband) if deadband > 0 else v
            return v * scale
        return _pipeline
