"""Analog input shaping pipeline.

Composes inversion, deadband, response curves, and scaling into a
single callable.  Pipeline order:

    inversion -> deadband -> curve -> scale

The pipeline is built once per action (or rebuilt when a property
changes at runtime) and called every cycle with the raw axis value.
"""

import logging
import math
from typing import Callable

from utils.math.curves import evaluate_segments, evaluate_spline
from utils.controller.model import EventTriggerMode

log = logging.getLogger("InputFactory")


class ShapingPipeline:
    """Callable shaping pipeline with a human-readable description."""

    __slots__ = ("_fn", "_description")

    def __init__(self, fn: Callable[[float], float], description: str):
        self._fn = fn
        self._description = description

    def __call__(self, raw: float) -> float:
        return self._fn(raw)

    def __str__(self) -> str:
        return self._description


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
    action_name: str = "",
) -> Callable[[float], float]:
    """Compose a full analog shaping pipeline into a single closure.

    Args:
        inversion: If True, negate the raw input before processing.
        deadband: Deadband threshold (0.0 to disable).
        trigger_mode: Determines the response curve applied.
        scale: Output multiplier applied after the curve.
        extra: ActionDefinition.extra dict containing spline_points
               and/or segment_points for SPLINE/SEGMENTED modes.
        action_name: Optional action name for diagnostic messages.

    Returns:
        A callable ``(float) -> float`` that transforms raw input.

    Pipeline stages by EventTriggerMode:
        RAW:       true passthrough — no shaping applied
        SCALED:    inversion -> deadband -> scale
        SQUARED:   inversion -> deadband -> squared -> scale
        SPLINE:    inversion -> deadband -> spline -> scale
        SEGMENTED: inversion -> deadband -> segments -> scale

    SPLINE/SEGMENTED fall back to SCALED if curve data is missing.
    """
    ctx = f" (action '{action_name}')" if action_name else ""
    # RAW — true passthrough, no shaping at all
    if trigger_mode == EventTriggerMode.RAW:
        return ShapingPipeline(lambda raw: raw, "raw passthrough")

    # Pre-resolve curve data so closures don't re-lookup each cycle
    spline_pts = extra.get("spline_points") if extra else None
    segment_pts = extra.get("segment_points") if extra else None

    # Build description stages list
    stages = []
    if inversion:
        stages.append("invert")
    if deadband > 0:
        stages.append(f"deadband({deadband})")
    mode_name = trigger_mode.value

    if trigger_mode == EventTriggerMode.SQUARED:
        stages.append("squared")
        if scale != 1.0:
            stages.append(f"scale({scale})")

        def _pipeline(raw: float) -> float:
            v = -raw if inversion else raw
            v = apply_deadband(v, deadband) if deadband > 0 else v
            v = curve_squared(v)
            return v * scale
        desc = " -> ".join(stages) if stages else mode_name
        return ShapingPipeline(_pipeline, desc)

    elif trigger_mode == EventTriggerMode.SPLINE:
        if not spline_pts:
            log.warning(
                "SPLINE trigger mode has no spline_points data%s — "
                "falling back to SCALED behavior", ctx)
        else:
            stages.append(f"spline({len(spline_pts)}pts)")
            if scale != 1.0:
                stages.append(f"scale({scale})")

            def _pipeline(raw: float) -> float:
                v = -raw if inversion else raw
                v = apply_deadband(v, deadband) if deadband > 0 else v
                v = evaluate_spline(spline_pts, v)
                return v * scale
            desc = " -> ".join(stages) if stages else mode_name
            return ShapingPipeline(_pipeline, desc)

    elif trigger_mode == EventTriggerMode.SEGMENTED:
        if not segment_pts:
            log.warning(
                "SEGMENTED trigger mode has no segment_points data%s — "
                "falling back to SCALED behavior", ctx)
        else:
            stages.append(f"segments({len(segment_pts)}pts)")
            if scale != 1.0:
                stages.append(f"scale({scale})")

            def _pipeline(raw: float) -> float:
                v = -raw if inversion else raw
                v = apply_deadband(v, deadband) if deadband > 0 else v
                v = evaluate_segments(segment_pts, v)
                return v * scale
            desc = " -> ".join(stages) if stages else mode_name
            return ShapingPipeline(_pipeline, desc)

    # SCALED (and fallback for SPLINE/SEGMENTED with missing data)
    if scale != 1.0:
        stages.append(f"scale({scale})")

    def _pipeline(raw: float) -> float:
        v = -raw if inversion else raw
        v = apply_deadband(v, deadband) if deadband > 0 else v
        return v * scale
    desc = " -> ".join(stages) if stages else "scaled"
    return ShapingPipeline(_pipeline, desc)
