"""
Robot constants package.

Sub-modules:
  robot_constants   - Physical constants for the overall robot chassis
  swerve_constants  - Swerve drivetrain constants and module name identifiers

All names are re-exported here so existing imports continue to work:
  from constants import SwerveDriveConsts        # unchanged
  from constants import SwerveModuleName         # new
"""

from .robot_constants import RobotConstants
from .swerve_constants import (
    CaptainPlanetConsts,
    SwerveModuleName,
    SwerveDriveConsts,
    SwerveModuleMk4iConsts,
    SwerveModuleMk4iL1Consts,
    SwerveModuleMk4iL2Consts,
)

__all__ = [
    "CaptainPlanetConsts",
    "RobotConstants",
    "SwerveModuleName",
    "SwerveDriveConsts",
    "SwerveModuleMk4iConsts",
    "SwerveModuleMk4iL1Consts",
    "SwerveModuleMk4iL2Consts",
]
