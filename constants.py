"""
Collection of numeric constants that define physical properties of the robot
"""

# Native imports
import math


# Third-Party Imports



#############################
# ROBOT ###################
#############################


class RobotConstants:
    massKG: float = 63.9565
    #MOI: Moment of inertia, kg*m^2
    MOI: float = 5.94175290870316


#############################
# SWERVE ###################
#############################


class SwerveDriveConsts(RobotConstants):
    # where the wheel is compared to the center of the robot in meters
    moduleFrontLeftX: float = 0.31115
    moduleFrontLeftY: float = 0.26035
    moduleFrontRightX: float = 0.31115
    moduleFrontRightY: float = -0.26035
    moduleBackLeftX: float = -0.31115
    moduleBackLeftY: float = 0.26035
    moduleBackRightX: float = -0.31115
    moduleBackRightY: float = -0.26035

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

    maxTranslationMPS: float = 4.14528
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
    wheelCOF: float = 1.00548
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
