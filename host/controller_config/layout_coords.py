"""Pixel coordinates for Xbox controller inputs on the SVG image.

Coordinates are relative to the SVG viewport (744 x 500).
Each input defines:
  - anchor: where the line starts on the controller image
  - label: where the binding box is drawn (outside the controller)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class InputCoord:
    """Position data for a single controller input."""
    name: str
    display_name: str
    input_type: str  # "button", "axis", "pov"
    anchor_x: float
    anchor_y: float
    label_x: float
    label_y: float


# Coordinates tuned against images/Xbox_Controller.svg (744 x 500 viewport).
# Anchors are on the controller; labels are placed along the edges.

XBOX_INPUTS: list[InputCoord] = [
    # --- Axes ---
    # Left stick (X and Y shown separately, anchored at stick center)
    InputCoord("left_stick_x", "Left Stick X", "axis",
               215, 240, 15, 190),
    InputCoord("left_stick_y", "Left Stick Y", "axis",
               215, 240, 15, 230),
    # Right stick
    InputCoord("right_stick_x", "Right Stick X", "axis",
               450, 345, 715, 330),
    InputCoord("right_stick_y", "Right Stick Y", "axis",
               450, 345, 715, 370),
    # Triggers
    InputCoord("left_trigger", "Left Trigger", "axis",
               145, 55, 15, 30),
    InputCoord("right_trigger", "Right Trigger", "axis",
               595, 55, 715, 30),

    # --- Buttons ---
    InputCoord("a_button", "A Button", "button",
               535, 280, 715, 270),
    InputCoord("b_button", "B Button", "button",
               570, 240, 715, 230),
    InputCoord("x_button", "X Button", "button",
               500, 240, 715, 190),
    InputCoord("y_button", "Y Button", "button",
               535, 200, 715, 150),
    InputCoord("left_bumper", "Left Bumper", "button",
               180, 115, 15, 80),
    InputCoord("right_bumper", "Right Bumper", "button",
               565, 115, 715, 80),
    InputCoord("back_button", "Back", "button",
               305, 245, 15, 290),
    InputCoord("start_button", "Start", "button",
               430, 245, 715, 110),
    InputCoord("left_stick_button", "Left Stick Press", "button",
               215, 240, 15, 150),
    InputCoord("right_stick_button", "Right Stick Press", "button",
               450, 345, 715, 410),

    # --- POV / D-pad ---
    InputCoord("pov_up", "D-Pad Up", "pov",
               275, 315, 15, 340),
    InputCoord("pov_down", "D-Pad Down", "pov",
               275, 370, 15, 420),
    InputCoord("pov_left", "D-Pad Left", "pov",
               250, 340, 15, 380),
    InputCoord("pov_right", "D-Pad Right", "pov",
               300, 340, 15, 460),
]

# Quick lookup by input name
XBOX_INPUT_MAP: dict[str, InputCoord] = {inp.name: inp for inp in XBOX_INPUTS}

# Canonical list of all input names
XBOX_INPUT_NAMES: list[str] = [inp.name for inp in XBOX_INPUTS]
