"""VirtualAnalogGenerator — converts button presses into ramped analog values.

Maintains position (output) and velocity (rate of change) each update cycle.

Button modes (va_button_mode):
- "held" (default): active while button is held, deactivates on release
- "toggle":         each press toggles between active and inactive

Ramp modes (mutually exclusive — if both set, ramp_rate wins with a warning):
- ramp_rate > 0:     constant velocity (triangle wave), capped at ramp_rate
- acceleration > 0:  v = u + a*t, velocity builds with no cap (hyperbolic curve)
- both 0:            instant jump to target

Button deactivated -> decelerate toward rest_value:
- zero_vel_on_release: velocity zeroed immediately, then decelerate
- Uses negative_ramp_rate (falls back to ramp_rate)
- Uses negative_acceleration (falls back to acceleration)
- Both 0: instant jump to rest_value

Output is clamped to [min(rest, target), max(rest, target)].

The generator output feeds into the existing shaping pipeline as the
"raw" input: generator -> inversion -> deadband -> curve -> scale -> slew

Uses FPGA time on both real hardware and robotpy sim. Falls back to
default_dt only in pure-Python tests or the GUI tool where wpilib
Timer is unavailable.
"""

import warnings
from typing import Callable

from utils.controller.model import (
    ActionDefinition,
    EXTRA_VA_RAMP_RATE,
    EXTRA_VA_ACCELERATION,
    EXTRA_VA_NEGATIVE_RAMP_RATE,
    EXTRA_VA_NEGATIVE_ACCELERATION,
    EXTRA_VA_ZERO_VEL_ON_RELEASE,
    EXTRA_VA_TARGET_VALUE,
    EXTRA_VA_REST_VALUE,
    EXTRA_VA_BUTTON_MODE,
)

# Try to import wpilib.Timer for FPGA time; None if unavailable
try:
    import wpilib
    _get_time = wpilib.Timer.getFPGATimestamp
except ImportError:
    _get_time = None


class VirtualAnalogGenerator:
    """Generates a ramped analog value from a boolean button input.

    Args:
        action: The ActionDefinition containing VA parameters in extra dict.
        button_fn: Callable returning True when the button is pressed.
        default_dt: Fallback time step (seconds) when FPGA time is unavailable.
    """

    def __init__(
        self,
        action: ActionDefinition,
        button_fn: Callable[[], bool],
        default_dt: float = 0.02,
    ):
        extra = action.extra or {}

        self._button_fn = button_fn
        self._default_dt = default_dt

        # Physics parameters — ramp_rate and acceleration are mutually exclusive
        self._ramp_rate = float(extra.get(EXTRA_VA_RAMP_RATE, 0.0))
        self._acceleration = float(extra.get(EXTRA_VA_ACCELERATION, 0.0))
        if self._ramp_rate > 0 and self._acceleration > 0:
            name = getattr(action, 'name', '?')
            warnings.warn(
                f"VA action '{name}': both ramp_rate and acceleration set. "
                f"Using ramp_rate ({self._ramp_rate}), ignoring acceleration."
            )
        neg_ramp = extra.get(EXTRA_VA_NEGATIVE_RAMP_RATE)
        self._negative_ramp_rate = (
            float(neg_ramp) if neg_ramp is not None else self._ramp_rate)
        neg_accel = extra.get(EXTRA_VA_NEGATIVE_ACCELERATION)
        self._negative_acceleration = (
            float(neg_accel) if neg_accel is not None else self._acceleration)
        self._zero_vel_on_release = bool(
            extra.get(EXTRA_VA_ZERO_VEL_ON_RELEASE, False))
        self._target_value = float(extra.get(EXTRA_VA_TARGET_VALUE, 1.0))
        self._rest_value = float(extra.get(EXTRA_VA_REST_VALUE, 0.0))
        self._toggle_mode = (
            extra.get(EXTRA_VA_BUTTON_MODE, "held") == "toggle")

        # Clamp bounds
        self._min_val = min(self._rest_value, self._target_value)
        self._max_val = max(self._rest_value, self._target_value)

        # State
        self._position = self._rest_value
        self._velocity = 0.0
        self._was_pressed = False
        self._toggle_active = False  # toggle state (for toggle mode)
        self._last_time = None  # FPGA timestamp of last update

    def update(self) -> None:
        """Advance the physics simulation one step.

        Call once per robot cycle, before reading get_value().
        """
        # Compute dt
        dt = self._default_dt
        if _get_time is not None:
            now = _get_time()
            if self._last_time is not None:
                dt = now - self._last_time
                if dt <= 0:
                    dt = self._default_dt
            self._last_time = now

        raw_pressed = self._button_fn()

        # Determine effective active state
        was_active = self._toggle_active if self._toggle_mode else self._was_pressed
        if self._toggle_mode:
            if raw_pressed and not self._was_pressed:
                self._toggle_active = not self._toggle_active
            active = self._toggle_active
        else:
            active = raw_pressed
        self._was_pressed = raw_pressed

        # Zero velocity on deactivation edge
        if was_active and not active and self._zero_vel_on_release:
            self._velocity = 0.0

        if active:
            self._update_toward(
                self._target_value,
                self._ramp_rate,
                self._acceleration,
                dt,
            )
        else:
            self._update_toward(
                self._rest_value,
                self._negative_ramp_rate,
                self._negative_acceleration,
                dt,
            )

        # Clamp — zero velocity when hitting a limit
        clamped = max(self._min_val, min(self._max_val, self._position))
        if clamped != self._position:
            self._velocity = 0.0
            self._position = clamped

    def _update_toward(
        self,
        target: float,
        max_speed: float,
        accel: float,
        dt: float,
    ) -> None:
        """Move position toward target using velocity/acceleration model.

        Modes (mutually exclusive):
          - Both 0:        instant jump to target
          - max_speed > 0: constant velocity (triangle wave), accel ignored
          - accel > 0:     v = u + a*t, no velocity cap (hyperbolic curve)
        """
        # Already at target
        diff = target - self._position
        if abs(diff) < 1e-9:
            self._position = target
            self._velocity = 0.0
            return

        direction = 1.0 if diff > 0 else -1.0

        if max_speed > 0.0:
            # Constant velocity (triangle wave) — ramp_rate takes priority
            self._velocity = direction * max_speed
        elif accel > 0.0:
            # Acceleration mode — v = u + a*t, no cap
            self._velocity += direction * accel * dt
        else:
            # Both zero — instant jump
            self._position = target
            self._velocity = 0.0
            return

        # Update position
        self._position += self._velocity * dt

        # Don't overshoot target
        new_diff = target - self._position
        if (direction > 0 and new_diff < 0) or \
           (direction < 0 and new_diff > 0):
            self._position = target
            self._velocity = 0.0

    def get_value(self) -> float:
        """Return the current output position."""
        return self._position

    def reset(self) -> None:
        """Reset to rest position with zero velocity."""
        self._position = self._rest_value
        self._velocity = 0.0
        self._last_time = None
        self._was_pressed = False
        self._toggle_active = False


# ---------------------------------------------------------------------------
# Pure-Python simulation for GUI visualization (no wpilib dependency)
# ---------------------------------------------------------------------------

def simulate_va_ramp(
    ramp_rate: float = 0.0,
    acceleration: float = 0.0,
    negative_ramp_rate: float | None = None,
    negative_acceleration: float | None = None,
    zero_vel_on_release: bool = False,
    target_value: float = 1.0,
    rest_value: float = 0.0,
    total_duration: float = 3.0,
    press_duration: float = 1.5,
    dt: float = 0.005,
) -> list[tuple[float, float]]:
    """Simulate a VA ramp cycle for visualization.

    Simulates button released from t=0 to t=press_duration (target→rest),
    then pressed from t=press_duration onward (rest→target).
    Returns list of (time, position) tuples for plotting.
    Pure Python — no wpilib dependency.
    """
    neg_ramp = negative_ramp_rate if negative_ramp_rate is not None else ramp_rate
    neg_accel = (negative_acceleration if negative_acceleration is not None
                 else acceleration)
    min_val = min(rest_value, target_value)
    max_val = max(rest_value, target_value)

    position = target_value
    velocity = 0.0
    was_pressed = True
    points = [(0.0, position)]

    t = 0.0
    while t < total_duration:
        t += dt
        pressed = t > press_duration

        # Zero velocity on release edge
        if was_pressed and not pressed and zero_vel_on_release:
            velocity = 0.0
        was_pressed = pressed

        if pressed:
            target = target_value
            max_spd = ramp_rate
            acc = acceleration
        else:
            target = rest_value
            max_spd = neg_ramp
            acc = neg_accel

        # Physics step — modes are mutually exclusive:
        #   max_spd > 0: constant velocity (triangle wave)
        #   acc > 0:     v = u + a*t, no cap (hyperbolic curve)
        #   both 0:      instant jump
        diff = target - position
        if abs(diff) < 1e-9:
            position = target
            velocity = 0.0
        elif max_spd == 0.0 and acc == 0.0:
            position = target
            velocity = 0.0
        else:
            direction = 1.0 if diff > 0 else -1.0
            if max_spd > 0.0:
                velocity = direction * max_spd
            else:
                velocity += direction * acc * dt
            position += velocity * dt
            # Don't overshoot
            new_diff = target - position
            if (direction > 0 and new_diff < 0) or \
               (direction < 0 and new_diff > 0):
                position = target
                velocity = 0.0

        clamped = max(min_val, min(max_val, position))
        if clamped != position:
            velocity = 0.0
            position = clamped
        points.append((t, position))

    return points
