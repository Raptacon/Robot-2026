"""
Robot constants package.

Sub-modules:
  robot_constants   - Physical constants for the overall robot chassis
  robot_geometry    - Robot frame, module positions, camera mounts, mechanisms
  swerve_constants  - Swerve drivetrain constants and module name identifiers

All names are re-exported here so existing imports continue to work:
  from constants import SwerveDriveConsts        # unchanged
  from constants import SwerveModuleName         # new
"""

from .robot_constants import RobotConstants
from .robot_geometry import (
    ROBOT_WIDTH_M,
    ROBOT_LENGTH_M,
    SWERVE_MODULE_POSITIONS,
    CAMERAS,
    MECHANISMS,
    get_camera,
)
from .robot_geometry import ROBOT_TO_TURRET, TURRET_TO_HOOD
from utils.geometry import (
    CameraGeometry,
    MechanismMount,
    MechanismGeometry,  # backward compat alias
    camera_transform,
    transform_from_inches,
    chain_transforms,
    make_camera,
)
from .swerve_constants import (
    SwerveModuleName,
    SwerveDriveConsts,
    SwerveModuleMk4iConsts,
    SwerveModuleMk4iL1Consts,
    SwerveModuleMk4iL2Consts,
    IntakePivotConstants,
    IntakeRollerConstants,
    HopperConstants,
    ShooterConstants,
    FeedConstants,
)

__all__ = [
    "RobotConstants",
    "ROBOT_WIDTH_M",
    "ROBOT_LENGTH_M",
    "SWERVE_MODULE_POSITIONS",
    "CAMERAS",
    "MECHANISMS",
    "CameraGeometry",
    "MechanismMount",
    "MechanismGeometry",
    "get_camera",
    "camera_transform",
    "transform_from_inches",
    "chain_transforms",
    "make_camera",
    "ROBOT_TO_TURRET",
    "TURRET_TO_HOOD",
    "SwerveModuleName",
    "SwerveDriveConsts",
    "SwerveModuleMk4iConsts",
    "SwerveModuleMk4iL1Consts",
    "SwerveModuleMk4iL2Consts",
    "IntakePivotConstants",
    "IntakeRollerConstants",
    "HopperConstants",
    "ShooterConstants",
    "FeedConstants",
]
