"""
Robot physical geometry: frame dimensions, module positions, camera mounts,
and mechanism locations.

Values only — helper classes and transform builders live in utils/geometry.py.
Edit this file when hardware changes (camera repositioned, module swapped, etc.).

Coordinate system (WPI standard):
    +X = forward       +Y = left       +Z = up
"""

from wpimath.geometry import Translation2d

from utils.geometry import (
    CameraGeometry,
    MechanismMount,
    inches_to_meters,
    make_camera,
    transform_from_inches,
)


# ══════════════════════════════════════════════════════════════════════
#  ROBOT FRAME
# ══════════════════════════════════════════════════════════════════════

ROBOT_WIDTH_M = inches_to_meters(28.0)    # side-to-side (Y axis), 24"
ROBOT_LENGTH_M = inches_to_meters(26.5)   # front-to-back (X axis), 26.5"


# ══════════════════════════════════════════════════════════════════════
#  SWERVE MODULE POSITIONS
# ══════════════════════════════════════════════════════════════════════
# Wheel contact-patch locations relative to robot center.
# Define front-left, derive the other three by mirroring.
# Canonical source — swerve_constants.py derives its X/Y floats from here.

_MODULE_X = inches_to_meters(10.39)  # forward distance from center
_MODULE_Y = inches_to_meters(11.30)  # left distance from center

SWERVE_FL = Translation2d(_MODULE_X, _MODULE_Y)       # front-left
SWERVE_FR = Translation2d(_MODULE_X, -_MODULE_Y)      # mirror Y
SWERVE_BL = Translation2d(-_MODULE_X, _MODULE_Y)      # mirror X
SWERVE_BR = Translation2d(-_MODULE_X, -_MODULE_Y)     # mirror both

# Ordered FL, FR, BL, BR (WPILib convention)
SWERVE_MODULE_POSITIONS = [SWERVE_FL, SWERVE_FR, SWERVE_BL, SWERVE_BR]
SWERVE_MODULE_NAMES = ["Front Left", "Front Right", "Back Left", "Back Right"]


# ══════════════════════════════════════════════════════════════════════
#  CAMERAS
# ══════════════════════════════════════════════════════════════════════

CAMERAS = [
    make_camera(
        "Side_Camera",
        x_in=-6.0,           # 6" toward rear
        y_in=12.0,           # 12" toward left side
        z_in=12.0,           # 12" above center plane
        pitch_up_deg=15.0,   # 15 deg tilt up
        yaw_deg=90.0,        # facing left
        fov_deg=70.0,
    ),
    make_camera(
        "Back_Camera",
        x_in=-9.0,           # 9" toward rear
        y_in=7.5,            # 7.5" toward left side
        z_in=10.5,           # ~10.5" up
        pitch_up_deg=15.0,   # 15 deg tilt up
        yaw_deg=180.0,       # facing backward
        fov_deg=70.0,
    ),
]


def get_camera(name: str) -> CameraGeometry:
    """Look up a camera by name. Raises KeyError if not found."""
    for cam in CAMERAS:
        if cam.name == name:
            return cam
    raise KeyError(f"No camera '{name}'. "
                   f"Available: {[c.name for c in CAMERAS]}")


# ══════════════════════════════════════════════════════════════════════
#  MECHANISM TRANSFORMS
# ══════════════════════════════════════════════════════════════════════
# Each mechanism has a Transform3d relative to its parent frame.
# robot center is the default parent. Use parent_transform to chain.

# Turret: positioned relative to robot center
ROBOT_TO_TURRET = transform_from_inches(
    x_in=-6.0,           # 2" behind center
    y_in=5.0,
    z_in=16.0,            # 6" up
)

# Hood: positioned relative to turret
TURRET_TO_HOOD = transform_from_inches(
    z_in=2.0,            # 2" above turret center
    x_in=-6.5/2
)


# ══════════════════════════════════════════════════════════════════════
#  MECHANISM VISUALIZATION LIST
# ══════════════════════════════════════════════════════════════════════
# Combines transforms with visualization metadata for the visualizer.

# Swerve modules from canonical positions (2D → 3D with z=0)
_swerve_mechanisms = [
    MechanismMount(
        name, "swerve_module",
        transform_from_inches(
            x_in=pos.X() / 0.0254,
            y_in=pos.Y() / 0.0254,
        ),
        width_in=3.0, length_in=4.0, color="#aaaa44",
    )
    for name, pos in zip(SWERVE_MODULE_NAMES, SWERVE_MODULE_POSITIONS)
]

# Turret: transform from robot center
_turret = MechanismMount(
    "Turret", "turret",
    ROBOT_TO_TURRET,
    radius_in=6.0, color="#cc5555",
)

# Hood: transform relative to turret (chained)
_hood = MechanismMount(
    "Hood", "generic",
    TURRET_TO_HOOD,
    parent_transform=ROBOT_TO_TURRET,
    parent_name="Turret",
    width_in=3.0, length_in=2.0, color="#cc8855",
)

MECHANISMS = _swerve_mechanisms + [_turret, _hood]
