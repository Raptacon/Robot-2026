"""
Physical constants and identifiers for the swerve drivetrain.
"""

# Native imports
import math
from enum import Enum, StrEnum

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
    # where each module is compared to the center of the robot, in meters (x, y)
    moduleLocations = {
        SwerveModuleName.FRONT_LEFT: (0.31115, 0.26035),
        SwerveModuleName.FRONT_RIGHT: (0.31115, -0.26035),
        SwerveModuleName.BACK_LEFT: (-0.31115, 0.26035),
        SwerveModuleName.BACK_RIGHT: (-0.31115, -0.26035),
    }

    # inverts if the module or gyro does not rotate counterclockwise positive
    invertGyro: bool = False
    moduleInvertDrive = {
        SwerveModuleName.FRONT_LEFT: True,
        SwerveModuleName.FRONT_RIGHT: True,
        SwerveModuleName.BACK_LEFT: True,
        SwerveModuleName.BACK_RIGHT: True,
    }
    moduleInvertSteer = {
        SwerveModuleName.FRONT_LEFT: True,
        SwerveModuleName.FRONT_RIGHT: True,
        SwerveModuleName.BACK_LEFT: True,
        SwerveModuleName.BACK_RIGHT: True,
    }

    maxTranslationMPS: float = 4.6
    maxAngularDPS: float = math.degrees(
        maxTranslationMPS / math.hypot(*moduleLocations[SwerveModuleName.FRONT_LEFT])
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


class CaptainPlanetConsts:
    kIntakeMotorCanId = 40
    kRollerMotorCanId = 41
    kMotorInverted = False
    kCurrentLimitAmps = 30
    # kBreakBeam = 2
    # kFrontBreakBeam = 2
    # kBackBreakBeam = 0
    # kHallEffectSensor = 6
    kDefaultSpeed = 0.15
    kOperatorDampener = 0.15
    class BreakBeamActionOptions(Enum):
        DONOTHING = 1
        TOFRONT = 2
        TOBACK = 3
