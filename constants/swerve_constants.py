"""
Physical constants and identifiers for the swerve drivetrain.
"""

# Native imports
import math
from enum import StrEnum

# Third-party imports
import rev

# Internal imports
from .robot_constants import RobotConstants


class SwerveModuleName(StrEnum):
    """Canonical string identifiers for each swerve module position.

    Values are the string names used in NetworkTables, SmartDashboard keys,
    and subsystem registration (e.g. "frontLeft").
    """
    FRONT_LEFT = "frontLeft"
    FRONT_RIGHT = "frontRight"
    BACK_LEFT = "backLeft"
    BACK_RIGHT = "backRight"


#############################
# SWERVE ###################
#############################


class SwerveDriveConsts(RobotConstants):
    # where the wheel is compared to the center of the robot in meters
    moduleFrontLeftX: float = 0.264
    moduleFrontLeftY: float = 0.287
    moduleFrontRightX: float = 0.264
    moduleFrontRightY: float = -0.287
    moduleBackLeftX: float = -0.264
    moduleBackLeftY: float = 0.287
    moduleBackRightX: float = -0.264
    moduleBackRightY: float = -0.287

    # inverts if the module or gyro does not rotate counterclockwise positive
    invertGyro: bool = False
    moduleFrontLeftInvertDrive: bool = True
    moduleFrontRightInvertDrive: bool = True
    moduleBackLeftInvertDrive: bool = True
    moduleBackRightInvertDrive: bool = True

    moduleFrontLeftInvertSteer: bool = True
    moduleFrontRightInvertSteer: bool = True
    moduleBackLeftInvertSteer: bool = True
    moduleBackRightInvertSteer: bool = True

    maxTranslationMPS: float = 4.6
    maxAngularDPS: float = math.degrees(
        maxTranslationMPS / math.hypot(moduleFrontLeftY, moduleFrontLeftX)
    )


class SwerveModuleMk4iConsts(SwerveDriveConsts):
    """
    https://github.com/SwerveDriveSpecialties/swerve-lib/blob/develop/src/main/java/com/swervedrivespecialties/swervelib/ctre/Falcon500DriveControllerFactoryBuilder.java
    """

    kNominalVoltage: float = 12.0
    # current limits use amps
    kDriveCurrentLimit: int = 40
    kSteerCurrentLimit: int = 20
    # ramp rate: how fast the bot can go from 0% to 100%, measured in seconds
    kRampRate: float = 0.25
    kTicksPerRotation: int = 1
    kCanStatusFrameHz: int = 10
    quadratureMeasurementRateMs: int = 10
    quadratureAverageDepth: int = 2
    numDriveMotors: int = 1
    motorType: str = "NEO"  # should be an option in wpimath.system.plant.DCMotor


class SwerveModuleMk4iL1Consts(SwerveModuleMk4iConsts):
    """
    https://docs.yagsl.com/configuring-yagsl/standard-conversion-factors
    """

    wheelDiameter: float = 0.10033  # in meters
    driveGearRatio: float = 8.14
    steerGearRatio: float = 150 / 7

    # position: meters per rotation
    # velocity: meters per second
    drivePositionConversionFactor: float = (math.pi * wheelDiameter) / (
        driveGearRatio * SwerveModuleMk4iConsts.kTicksPerRotation
    )
    driveVelocityConversionFactor: float = drivePositionConversionFactor / 60.0
    steerPositionConversionFactor: float = 360 / (
        steerGearRatio * SwerveModuleMk4iConsts.kTicksPerRotation
    )
    steerVelocityConversionFactor: float = steerPositionConversionFactor / 60.0

    moduleType: str = "Mk4i_L1"


class SwerveModuleMk4iL2Consts(SwerveModuleMk4iConsts):
    """
    https://docs.yagsl.com/configuring-yagsl/standard-conversion-factors
    """

    wheelDiameter: float = 0.10033  # in meters
    # COf: coefficient, force/force (no units)
    wheelCOF: float = 1.0130211
    driveGearRatio: float = 6.75
    steerGearRatio: float = 150 / 7

    # position: meters per rotation
    # velocity: meters per second
    drivePositionConversionFactor: float = (wheelCOF * (math.pi * wheelDiameter)) / (
        driveGearRatio * SwerveModuleMk4iConsts.kTicksPerRotation
    )
    driveVelocityConversionFactor: float = drivePositionConversionFactor / 60.0
    steerPositionConversionFactor: float = 360 / (
        steerGearRatio * SwerveModuleMk4iConsts.kTicksPerRotation
    )
    steerVelocityConversionFactor: float = steerPositionConversionFactor / 60.0

    moduleType: str = "Mk4i_L2"

#############################
# INTAKE ###################
#############################


class HoodConstants:
    motorId = 34
    inverted = False
    # Position conversion factor — set by calibration or known gear ratio.
    # Use PassiveRangeFinderCommand with full_range to measure this.
    positionConversionFactor = 9.53  # deg/rotation (from calibration)
    maxAngleDegrees = 20.0
    minAngleDegrees = 0.0


class IntakePivotConstants:
    name = "intake_pivot"
    canId = 20
    inverted = False
    motorClass = rev.SparkFlex
    currentLimitAmps = 30
    # Degrees per motor rotation — measure or calculate from gear ratio
    positionConversionFactor = 1.0  # TODO: calibrate on hardware
    # Mechanical safety boundaries (degrees)
    minSoftLimit = 0.0
    maxSoftLimit = 155.0
    # Target positions for commands (degrees)
    stowedPosition = 0.0
    deployedPosition = 155.0


class IntakeRollerConstants:
    name = "intake_roller"
    canId = 21
    inverted = False
    motorClass = rev.SparkFlex
    defaultPower = 0.6


class HopperConstants:
    name = "hopper"
    canId = 40
    inverted = True
    defaultPower = 0.5


class ShooterConstants:
    name = "shooter"
    flywheelLeadMotorId = 32
    flywheelFollowerMotorId = 33
    flywheelLeadInverted = False
    flywheelFollowerInverted = True
    currentLimitAmps = 40
    offsetDelta = 100
    fixedRPM = 6500
    # TODO: Get rest and max positions for shooter
    hoodRestPosition = 0
    hoodMaxPosition = 1
    hoodPosition1 = 0.25
    hoodPosition2 = 0.5
    hoodPosition3 = 0.75
    positionConversionFactor = 1 / 1.5


class FeedConstants:
    name = "feed"
    upperMotorId = 35
    lowerMotorId = 36
    upperInverted = True
    lowerInverted = True
    currentLimitAmps = 30
