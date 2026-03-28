# Native imports
from typing import Tuple

# Third-party imports
from wpimath.geometry import Rotation2d

class OperatorRobotConfig:
    # Default start position for red alliance using always-blue-alliance coordinates
    # Coordinates are x (meters), y (meters), and rotation (degrees)
    red_default_start_pose: Tuple[float] = (10.0, 1.5, 0.0)
    # Default start position for blue alliance using always-blue-alliance coordinates
    # Coordinates are x (meters), y (meters), and rotation (degrees)
    blue_default_start_pose: Tuple[float] = (7.7, 6.0, 180.0)
    # Give in front-left, front-right, back-left, back-right order
    # ids for the drive controllers
    swerve_module_channels: Tuple[int] = (50, 53, 56, 59)
    # Give in front-left, front-right, back-left, back-right order
    # starting rotational position for the absolute encoders
    swerve_abs_encoder_calibrations: Tuple[float] = (
        10.283203125 / 360.0, 323.6148 / 360.0,  347.2737188 / 360.0, 83.2865625 / 360.0
    )
    swerve_steer_pid: Tuple[float] = (0.011, 0, 0)
    swerve_drive_pid: Tuple[float] = (0.0021, 0, 0, 0) # TODO: tune PIDs
    pathplanner_translation_pid: Tuple[float] = (4.0, 0.0, 0.0)
    pathplanner_rotation_pid: Tuple[float] = (5.0, 0.0, 0.0)

    # Camera mount positions relative to robot center (x forward, y left, z up) in meters
    # and rotations (roll, pitch, yaw) in degrees.
    # TODO: Verify rotation angles match actual camera mounting orientation.
    back_cam_name: str = "Back_Camera"
    # Rear left corner: behind center (-X), left of center (+Y), above center (+Z)
    back_cam_translation: Tuple[float] = (-0.297, 0.297, 0.263)
    back_cam_rotation_deg: Tuple[float] = (0.0, 0.0, 0.0)

    side_cam_name: str = "Side_Camera"
    # Right side behind center: behind center (-X), right of center (-Y), above center (+Z)
    side_cam_translation: Tuple[float] = (-0.061, -0.320, 0.309)
    side_cam_rotation_deg: Tuple[float] = (0.0, 0.0, 0.0)

    # Vision filtering thresholds (see subsystem/localization/VISION.md)
    vision_ambiguity_threshold: float = 0.2
    vision_single_tag_max_distance_m: float = 4.0
    vision_field_border_margin_m: float = 0.5
    vision_max_z_error_m: float = 0.5
    vision_max_rotation_error_deg: float = 20.0

    # Dynamic standard deviation base values (x meters, y meters, theta radians)
    # See VISION.md for how these are scaled with distance.
    vision_single_tag_std_devs: Tuple[float] = (4.0, 4.0, float('inf'))
    vision_multi_tag_std_devs: Tuple[float] = (0.5, 0.5, 1.0)
    vision_std_dev_distance_factor: float = 30.0
    # First three elements are PID, last two elements are trapezoidal profile
    # Translation trapezoidal profile units are mps and mps^2, rotation are rps and rps^2
    pid_to_pose_translation_pid_profile: Tuple[float] = (2.0, 0.0, 0.0, 3, 1.5)
    pid_to_pose_rotation_pid_profile: Tuple[float] = (
        1.0, 0.0, 0.0, Rotation2d.fromDegrees(360).radians(), Rotation2d.fromDegrees(360).radians()
    )
    # Tolerance of x, y, and omega position errors within which robot is at target pose
    # x error is in meters, y error is in meters, omega error is in radians
    pid_to_pose_setpoint_tolerances: Tuple[float] = (0.25, 0.25, Rotation2d.fromDegrees(10).radians())

    # Robot motion constraints when running PathPlanner during teleop.
    # Values to give are: max translation velocity (mps), max translation acceleration (mps^2),
    # max angular velocity (dps), max angular acceleration (dps^2).
    teleop_pathplan_constraints: Tuple[float] = (2.5, 2.0, 360.0, 360.0)

    intake_pivot_pid: Tuple[float] = [0, 0, 0, 1 / 565]

class HoodConfig:
    # PID gains for hood position control (WPILib PIDController)
    hoodPID = (0.5, 0, 0)
    # ArmFeedforward gains: (kS, kG, kV, kA)
    # kS = static friction compensation (volts)
    # kG = gravity compensation at horizontal (volts)
    # kV = velocity feedforward (volts per deg/s)
    # kA = acceleration feedforward (volts per deg/s^2)
    hoodFeedforward = (0, 0, 0, 0)
    # Offset in degrees from hood 0-position to true horizontal.
    # 0 degrees hood position is approximately horizontal.
    # Positive degrees lift toward vertical.
    # ArmFeedforward expects 0 = horizontal, so this offset adjusts
    # the angle passed to the feedforward calculation.
    horizontalOffsetDegrees = 0.0


class ShooterConfig:
    # Configs for shooter
    shooterFeedMotorPIDF = (0, 0, 0, 1 / 473)
    shooterFlywheelMotorPIDF = (0, 0, 0, 1 / 560)
    shooterHoodMotorPIDF = (0, 0, 0, 1/917)
