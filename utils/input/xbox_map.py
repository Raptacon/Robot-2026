"""HID accessor tables for Xbox controllers.

Maps canonical input names (matching layout_coords.py XBOX_INPUT_NAMES)
to wpilib.XboxController method calls.  Pure data — no state.
"""

from typing import Callable

import wpilib


# --- Buttons (10) ---
# Each maps input_name -> callable(controller) -> bool
#
# These use raw state accessors (getAButton, etc.) — NOT the edge-detection
# variants (getAButtonPressed/Released).  Raw state is required because
# commands2.Trigger performs its own edge detection each cycle.  The
# pressed/released variants consume the event on read (return True only
# once per transition), which would conflict with Trigger's polling and
# cause missed events.

BUTTON_ACCESSORS: dict[str, Callable[[wpilib.XboxController], bool]] = {
    "a_button":           lambda c: c.getAButton(),
    "b_button":           lambda c: c.getBButton(),
    "x_button":           lambda c: c.getXButton(),
    "y_button":           lambda c: c.getYButton(),
    "left_bumper":        lambda c: c.getLeftBumper(),
    "right_bumper":       lambda c: c.getRightBumper(),
    "back_button":        lambda c: c.getBackButton(),
    "start_button":       lambda c: c.getStartButton(),
    "left_stick_button":  lambda c: c.getLeftStickButton(),
    "right_stick_button": lambda c: c.getRightStickButton(),
}


# --- Axes (6) ---
# Each maps input_name -> callable(controller) -> float

AXIS_ACCESSORS: dict[str, Callable[[wpilib.XboxController], float]] = {
    "left_stick_x":  lambda c: c.getLeftX(),
    "left_stick_y":  lambda c: c.getLeftY(),
    "right_stick_x": lambda c: c.getRightX(),
    "right_stick_y": lambda c: c.getRightY(),
    "left_trigger":  lambda c: c.getLeftTriggerAxis(),
    "right_trigger": lambda c: c.getRightTriggerAxis(),
}


# --- POV (8) ---
# Maps input_name -> angle in degrees (-1 = not pressed)

POV_ANGLE_MAP: dict[str, int] = {
    "pov_up":         0,
    "pov_up_right":   45,
    "pov_right":      90,
    "pov_down_right": 135,
    "pov_down":       180,
    "pov_down_left":  225,
    "pov_left":       270,
    "pov_up_left":    315,
}


# --- Outputs (3) ---
# Each maps output_name -> callable(controller, value) -> None

OUTPUT_ACCESSORS: dict[
    str, Callable[[wpilib.XboxController, float], None]
] = {
    "rumble_left": lambda c, v: c.setRumble(
        wpilib.XboxController.RumbleType.kLeftRumble, v),
    "rumble_right": lambda c, v: c.setRumble(
        wpilib.XboxController.RumbleType.kRightRumble, v),
    "rumble_both": lambda c, v: c.setRumble(
        wpilib.XboxController.RumbleType.kBothRumble, v),
}


# --- Aggregate sets (exported for use by validation.py) ---

ALL_INPUT_NAMES: set[str] = (
    set(BUTTON_ACCESSORS)
    | set(AXIS_ACCESSORS)
    | set(POV_ANGLE_MAP)
    | set(OUTPUT_ACCESSORS)
)


def get_input_category(name: str) -> str | None:
    """Return the category of an input name.

    Returns:
        "button", "axis", "pov", "output", or None if unknown.
    """
    if name in BUTTON_ACCESSORS:
        return "button"
    if name in AXIS_ACCESSORS:
        return "axis"
    if name in POV_ANGLE_MAP:
        return "pov"
    if name in OUTPUT_ACCESSORS:
        return "output"
    return None
