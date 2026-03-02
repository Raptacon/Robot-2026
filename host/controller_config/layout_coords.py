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
    # Left stick
    InputCoord("left_stick_x", "Left Stick X", "axis",
               _fx(420), _fy(695), _fx(219), _fy(768)),
    InputCoord("left_stick_y", "Left Stick Y", "axis",
               _fx(420), _fy(695), _fx(-80), _fy(646)),
    # Right stick
    InputCoord("right_stick_x", "Right Stick X", "axis",
               _fx(1210), _fy(965), _fx(1233), _fy(1100)),
    InputCoord("right_stick_y", "Right Stick Y", "axis",
               _fx(1210), _fy(965), _fx(1376), _fy(973)),
    # Triggers
    InputCoord("left_trigger", "Left Trigger", "axis",
               _fx(435), _fy(170), _fx(67), _fy(48)),
    InputCoord("right_trigger", "Right Trigger", "axis",
               _fx(1490), _fy(170), _fx(1501), _fy(43)),

    # --- Buttons ---
    InputCoord("a_button", "A Button", "button",
               _fx(1480), _fy(755), _fx(1864), _fy(716)),
    InputCoord("b_button", "B Button", "button",
               _fx(1629), _fy(633), _fx(1856), _fy(616)),
    InputCoord("x_button", "X Button", "button",
               _fx(1344), _fy(635), _fx(1830), _fy(465)),
    InputCoord("y_button", "Y Button", "button",
               _fx(1492), _fy(518), _fx(1782), _fy(302)),
    InputCoord("left_bumper", "Left Bumper", "button",
               _fx(455), _fy(290), _fx(-105), _fy(219)),
    InputCoord("right_bumper", "Right Bumper", "button",
               _fx(1465), _fy(290), _fx(1610), _fy(175)),
    InputCoord("back_button", "Back", "button",
               _fx(760), _fy(640), _fx(612), _fy(69)),
    InputCoord("start_button", "Start", "button",
               _fx(1160), _fy(640), _fx(998), _fy(71)),
    InputCoord("left_stick_button", "Left Stick Press", "button",
               _fx(420), _fy(695), _fx(355), _fy(453)),
    InputCoord("right_stick_button", "Right Stick Press", "button",
               _fx(1210), _fy(965), _fx(941), _fy(709)),

    # --- POV / D-pad (center ~683, 900) ---
    # D-pad directions are treated as buttons; the factory converts
    # the raw POV angle to individual boolean values at runtime.
    InputCoord("pov_up", "D-Pad Up", "button",
               _fx(683), _fy(840), _fx(496), _fy(1012)),
    InputCoord("pov_up_right", "D-Pad Up-Right", "button",
               _fx(740), _fy(840), _fx(685), _fy(1098)),
    InputCoord("pov_right", "D-Pad Right", "button",
               _fx(740), _fy(900), _fx(804), _fy(1191)),
    InputCoord("pov_down_right", "D-Pad Down-Right", "button",
               _fx(740), _fy(960), _fx(694), _fy(1310)),
    InputCoord("pov_down", "D-Pad Down", "button",
               _fx(683), _fy(960), _fx(504), _fy(1420)),
    InputCoord("pov_down_left", "D-Pad Down-Left", "button",
               _fx(626), _fy(960), _fx(292), _fy(1309)),
    InputCoord("pov_left", "D-Pad Left", "button",
               _fx(626), _fy(900), _fx(178), _fy(1198)),
    InputCoord("pov_up_left", "D-Pad Up-Left", "button",
               _fx(626), _fy(840), _fx(300), _fy(1091)),

    # --- Outputs (rumble) ---
    InputCoord("rumble_left", "Left Rumble", "output",
               _fx(700), _fy(-70), _fx(298), _fy(-172)),
    InputCoord("rumble_both", "Both Rumble", "output",
               _fx(960), _fy(-70), _fx(786), _fy(-191)),
    InputCoord("rumble_right", "Right Rumble", "output",
               _fx(1220), _fy(-70), _fx(1282), _fy(-163)),
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
