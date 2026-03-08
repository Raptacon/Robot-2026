"""Fractional coordinates for Xbox controller inputs on the controller image.

All coordinates are normalized fractions (0.0 to 1.0) of the image
dimensions. The canvas maps them to actual pixel positions based on
the current rendered image size, so they work at any resolution or
window size.

Each input defines:
  - anchor: where the line starts on the controller image (fraction)
  - label: where the binding box is drawn (fractions of image dimensions)

ButtonShape defines a clickable outline drawn on the controller image.
Multiple inputs can share a single shape (e.g., stick X, Y, and button).
"""

from dataclasses import dataclass, field

# Source image dimensions used to derive the fractions below.
# Only used as documentation; the code uses fractions directly.
_IMG_W = 1920
_IMG_H = 1292


def _fx(px: float) -> float:
    """Convert pixel X to fraction."""
    return px / _IMG_W


def _fy(py: float) -> float:
    """Convert pixel Y to fraction."""
    return py / _IMG_H


@dataclass(frozen=True)
class InputCoord:
    """Position data for a single controller input.

    anchor_x/y are fractions (0-1) of the image.
    label_x/y are fractions (0-1) of the image for binding box placement.
    """
    name: str
    display_name: str
    input_type: str  # "button", "axis", "pov"
    anchor_x: float
    anchor_y: float
    label_x: float
    label_y: float


@dataclass(frozen=True)
class ButtonShape:
    """A clickable outline drawn on the controller image.

    center_x/y and width/height are all fractions of image dimensions.
    """
    name: str
    shape: str              # "circle", "rect", "pill"
    center_x: float
    center_y: float
    width: float            # fraction of image width
    height: float           # fraction of image height
    inputs: list[str] = field(default_factory=list)


# Coordinates calibrated against images/Xbox_Controller.svg.png (1920x1292),
# then converted to fractions.

XBOX_INPUTS: list[InputCoord] = [
    # --- Axes ---
    # Left stick — labels in a vertical column, connector bar drawn separately
    InputCoord("left_stick_x", "Left Stick X", "axis",
               _fx(420), _fy(695), _fx(-382), _fy(287)),
    InputCoord("left_stick_y", "Left Stick Y", "axis",
               _fx(420), _fy(695), _fx(-382), _fy(416)),
    # Right stick — labels in a vertical column, connector bar drawn separately
    InputCoord("right_stick_x", "Right Stick X", "axis",
               _fx(1210), _fy(965), _fx(1646), _fy(1026)),
    InputCoord("right_stick_y", "Right Stick Y", "axis",
               _fx(1210), _fy(965), _fx(1646), _fy(1156)),
    # Triggers
    InputCoord("left_trigger", "Left Trigger", "axis",
               _fx(435), _fy(170), _fx(8), _fy(-2)),
    InputCoord("right_trigger", "Right Trigger", "axis",
               _fx(1490), _fy(170), _fx(1494), _fy(1)),

    # --- Buttons ---
    InputCoord("a_button", "A Button", "button",
               _fx(1480), _fy(755), _fx(1723), _fy(686)),
    InputCoord("b_button", "B Button", "button",
               _fx(1629), _fy(633), _fx(1715), _fy(558)),
    InputCoord("x_button", "X Button", "button",
               _fx(1344), _fy(635), _fx(1644), _fy(809)),
    InputCoord("y_button", "Y Button", "button",
               _fx(1492), _fy(518), _fx(1654), _fy(438)),
    InputCoord("left_bumper", "Left Bumper", "button",
               _fx(455), _fy(290), _fx(-113), _fy(147)),
    InputCoord("right_bumper", "Right Bumper", "button",
               _fx(1465), _fy(290), _fx(1556), _fy(169)),
    InputCoord("back_button", "Back", "button",
               _fx(760), _fy(640), _fx(560), _fy(108)),
    InputCoord("start_button", "Start", "button",
               _fx(1160), _fy(640), _fx(965), _fy(112)),
    InputCoord("left_stick_button", "Left Stick Press", "button",
               _fx(420), _fy(695), _fx(-382), _fy(547)),
    InputCoord("right_stick_button", "Right Stick Press", "button",
               _fx(1210), _fy(965), _fx(1646), _fy(1286)),

    # --- POV / D-pad (center ~683, 900) ---
    # D-pad directions are treated as buttons; the factory converts
    # the raw POV angle to individual boolean values at runtime.
    # Labels in a vertical column (clockwise from Up), compact single-action,
    # connected by a single leader line + bar (see _draw_connector_groups).
    # Dragged as a group (see _draw_input, _on_drag).
    InputCoord("pov_up", "D-Pad Up", "button",
               _fx(683), _fy(840), _fx(-369), _fy(723)),
    InputCoord("pov_up_right", "D-Pad Up-Right", "button",
               _fx(740), _fy(840), _fx(-369), _fy(793)),
    InputCoord("pov_right", "D-Pad Right", "button",
               _fx(740), _fy(900), _fx(-369), _fy(862)),
    InputCoord("pov_down_right", "D-Pad Down-Right", "button",
               _fx(740), _fy(960), _fx(-369), _fy(931)),
    InputCoord("pov_down", "D-Pad Down", "button",
               _fx(683), _fy(960), _fx(-369), _fy(1001)),
    InputCoord("pov_down_left", "D-Pad Down-Left", "button",
               _fx(626), _fy(960), _fx(-369), _fy(1070)),
    InputCoord("pov_left", "D-Pad Left", "button",
               _fx(626), _fy(900), _fx(-369), _fy(1139)),
    InputCoord("pov_up_left", "D-Pad Up-Left", "button",
               _fx(626), _fy(840), _fx(-369), _fy(1208)),

    # --- Outputs (rumble) ---
    InputCoord("rumble_left", "Left Rumble", "output",
               _fx(700), _fy(-70), _fx(254), _fy(-111)),
    InputCoord("rumble_both", "Both Rumble", "output",
               _fx(960), _fy(-70), _fx(770), _fy(-21)),
    InputCoord("rumble_right", "Right Rumble", "output",
               _fx(1220), _fy(-70), _fx(1275), _fy(-111)),
]

# Clickable outlines drawn on the controller image.
XBOX_SHAPES: list[ButtonShape] = [
    # Face buttons (centers from color-centroid detection on PNG)
    ButtonShape("a", "circle", _fx(1480), _fy(755),
                _fx(140), _fy(140), ["a_button"]),
    ButtonShape("b", "circle", _fx(1629), _fy(633),
                _fx(140), _fy(140), ["b_button"]),
    ButtonShape("x", "circle", _fx(1344), _fy(635),
                _fx(140), _fy(140), ["x_button"]),
    ButtonShape("y", "circle", _fx(1492), _fy(518),
                _fx(140), _fy(140), ["y_button"]),
    # Bumpers
    ButtonShape("lb", "pill", _fx(455), _fy(318),
                _fx(360), _fy(110), ["left_bumper"]),
    ButtonShape("rb", "pill", _fx(1465), _fy(318),
                _fx(360), _fy(110), ["right_bumper"]),
    # Triggers
    ButtonShape("lt", "rect", _fx(472), _fy(170),
                _fx(115), _fy(155), ["left_trigger"]),
    ButtonShape("rt", "rect", _fx(1443), _fy(170),
                _fx(115), _fy(155), ["right_trigger"]),
    # Sticks
    ButtonShape("ls", "circle", _fx(420), _fy(695),
                _fx(220), _fy(220),
                ["left_stick_x", "left_stick_y", "left_stick_button"]),
    ButtonShape("rs", "circle", _fx(1210), _fy(965),
                _fx(220), _fy(220),
                ["right_stick_x", "right_stick_y", "right_stick_button"]),
    # Back / Start
    ButtonShape("back", "circle", _fx(768), _fy(640),
                _fx(99), _fy(86), ["back_button"]),
    ButtonShape("start", "circle", _fx(1152), _fy(640),
                _fx(99), _fy(86), ["start_button"]),
    # D-pad — single circle around the whole pad; click opens direction menu
    ButtonShape("dpad", "circle", _fx(683), _fy(900),
                _fx(240), _fy(240),
                ["pov_up", "pov_up_right", "pov_right", "pov_down_right",
                 "pov_down", "pov_down_left", "pov_left", "pov_up_left"]),
    # Rumble — one rect per icon, each tied to a single channel
    ButtonShape("rumble_l", "rect", _fx(700), _fy(-70),
                _fx(80), _fy(80), ["rumble_left"]),
    ButtonShape("rumble_b", "rect", _fx(960), _fy(-70),
                _fx(80), _fy(80), ["rumble_both"]),
    ButtonShape("rumble_r", "rect", _fx(1220), _fy(-70),
                _fx(80), _fy(80), ["rumble_right"]),
]

# Quick lookup by input name
XBOX_INPUT_MAP: dict[str, InputCoord] = {inp.name: inp for inp in XBOX_INPUTS}

# Canonical list of all input names
XBOX_INPUT_NAMES: list[str] = [inp.name for inp in XBOX_INPUTS]
