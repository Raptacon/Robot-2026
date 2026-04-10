"""
Geometry helper classes and transform builders for robot physical layout.

Provides:
  - transform_from_inches(): general-purpose Transform3d builder
  - CameraGeometry: camera with transform + FOV
  - MechanismMount: any physical mechanism with transform, supports parent chains

The actual robot-specific values live in constants/robot_geometry.py.
"""

from wpimath.geometry import (
    Pose3d,
    Rotation3d,
    Transform3d,
    Translation3d,
)


# ── Conversion constant ──────────────────────────────────────────────

INCHES_TO_METERS = 0.0254


# ── Transform builders ───────────────────────────────────────────────

def inches_to_meters(inches: float) -> float:
    return inches * INCHES_TO_METERS


def transform_from_inches(
    x_in: float = 0,
    y_in: float = 0,
    z_in: float = 0,
    roll_deg: float = 0,
    pitch_up_deg: float = 0,
    yaw_deg: float = 0,
) -> Transform3d:
    """Build a Transform3d from inches and intuitive degree conventions.

    This is the general-purpose builder for any robot-relative transform:
    cameras, turrets, hoods, sensors, etc.

    Args:
        x_in: forward/back in inches (positive = forward)
        y_in: left/right in inches (positive = left)
        z_in: height in inches (positive = up)
        roll_deg: rotation about forward axis
        pitch_up_deg: positive = tilts UP (negated internally for WPI)
        yaw_deg: 0 = forward, 90 = left, 180 = backward

    Returns:
        Transform3d suitable for use as robot_to_X or parent_to_child.
    """
    c = INCHES_TO_METERS
    return Transform3d(
        Translation3d(x_in * c, y_in * c, z_in * c),
        Rotation3d.fromDegrees(roll_deg, -pitch_up_deg, yaw_deg),
    )


# Keep the old name as an alias for backward compat
camera_transform = transform_from_inches


def chain_transforms(*transforms: Transform3d) -> Transform3d:
    """Chain multiple transforms: parent_to_A + A_to_B + ... = parent_to_final.

    Uses Pose3d as the accumulator since WPILib Transform3d doesn't
    support direct addition.
    """
    result = Pose3d()
    for tf in transforms:
        result = result.transformBy(tf)
    return Transform3d(Pose3d(), result)


# ── Camera geometry ──────────────────────────────────────────────────

class CameraGeometry:
    """A vision camera on the robot.

    Stores the canonical WPILib Transform3d plus the original inch/degree
    values for display, serialization, and the visualizer.
    """

    __slots__ = ('name', 'robot_to_camera', 'fov_deg',
                 '_x_in', '_y_in', '_z_in',
                 '_roll_deg', '_pitch_up_deg', '_yaw_deg')

    def __init__(
        self,
        name: str,
        robot_to_camera: Transform3d,
        fov_deg: float = 70.0,
        *,
        x_in: float = 0, y_in: float = 0, z_in: float = 0,
        roll_deg: float = 0, pitch_up_deg: float = 0, yaw_deg: float = 0,
    ):
        self.name = name
        self.robot_to_camera = robot_to_camera
        self.fov_deg = fov_deg
        self._x_in = x_in
        self._y_in = y_in
        self._z_in = z_in
        self._roll_deg = roll_deg
        self._pitch_up_deg = pitch_up_deg
        self._yaw_deg = yaw_deg

    def to_dict(self) -> dict:
        """Serialize for the visualizer JSON."""
        t = self.robot_to_camera.translation()
        return {
            "name": self.name,
            "x_inches": self._x_in,
            "y_inches": self._y_in,
            "z_inches": self._z_in,
            "roll_deg": self._roll_deg,
            "pitch_deg": self._pitch_up_deg,
            "yaw_deg": self._yaw_deg,
            "fov_deg": self.fov_deg,
            "x_meters": round(t.X(), 4),
            "y_meters": round(t.Y(), 4),
            "z_meters": round(t.Z(), 4),
            "wpi_rotation_deg": {
                "roll": self._roll_deg,
                "pitch": -self._pitch_up_deg,
                "yaw": self._yaw_deg,
            },
        }


def make_camera(
    name: str,
    x_in: float = 0,
    y_in: float = 0,
    z_in: float = 0,
    roll_deg: float = 0,
    pitch_up_deg: float = 0,
    yaw_deg: float = 0,
    fov_deg: float = 70.0,
) -> CameraGeometry:
    """Create a CameraGeometry from inches and intuitive degrees."""
    tf = transform_from_inches(
        x_in, y_in, z_in, roll_deg, pitch_up_deg, yaw_deg
    )
    return CameraGeometry(
        name, tf, fov_deg,
        x_in=x_in, y_in=y_in, z_in=z_in,
        roll_deg=roll_deg, pitch_up_deg=pitch_up_deg, yaw_deg=yaw_deg,
    )


# ── Mechanism mount ──────────────────────────────────────────────────

class MechanismMount:
    """A physical mechanism on the robot.

    Each mechanism has:
      - A local transform (relative to its parent frame)
      - A resolved robot_to_mechanism transform (absolute from robot center)
      - Visualization properties (type, size, color)

    Supported types for the visualizer:
      "swerve_module" - block with wheel direction arrow
      "turret"        - circle with heading arrow
      "generic"       - labeled block

    Parent chaining example:
        turret is at robot_to_turret
        hood is at turret_to_hood (relative to turret)
        hood's robot_to_mechanism = robot_to_turret + turret_to_hood
    """

    __slots__ = ('name', 'type', 'local_transform', 'robot_to_mechanism',
                 'parent_name', 'width_m', 'length_m', 'radius_m', 'color')

    def __init__(
        self,
        name: str,
        mech_type: str,
        local_transform: Transform3d,
        *,
        parent_transform: Transform3d = None,
        parent_name: str = None,
        width_in: float = 3.0,
        length_in: float = 3.0,
        radius_in: float = 0,
        color: str = "",
    ):
        self.name = name
        self.type = mech_type
        self.local_transform = local_transform
        self.parent_name = parent_name

        # Resolve absolute transform from robot center
        if parent_transform is not None:
            self.robot_to_mechanism = chain_transforms(
                parent_transform, local_transform
            )
        else:
            self.robot_to_mechanism = local_transform

        c = INCHES_TO_METERS
        self.width_m = width_in * c
        self.length_m = length_in * c
        self.radius_m = radius_in * c
        self.color = color

    def to_dict(self) -> dict:
        c = INCHES_TO_METERS
        t = self.robot_to_mechanism.translation()
        r = self.robot_to_mechanism.rotation()
        return {
            "name": self.name,
            "type": self.type,
            "parent": self.parent_name,
            "x_inches": round(t.X() / c, 2),
            "y_inches": round(t.Y() / c, 2),
            "z_inches": round(t.Z() / c, 2),
            "yaw_deg": round(r.z_degrees, 2),
            "width_inches": round(self.width_m / c, 2),
            "length_inches": round(self.length_m / c, 2),
            "radius_inches": round(self.radius_m / c, 2),
            "color": self.color,
            "x_meters": round(t.X(), 4),
            "y_meters": round(t.Y(), 4),
            "z_meters": round(t.Z(), 4),
            "width_meters": round(self.width_m, 4),
            "length_meters": round(self.length_m, 4),
            "radius_meters": round(self.radius_m, 4),
        }


# Convenience alias kept for old imports
MechanismGeometry = MechanismMount
