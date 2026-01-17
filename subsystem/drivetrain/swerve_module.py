# Native imports
from typing import Tuple

# Internal imports
from config import OperatorRobotConfig
from constants import SwerveModuleMk4iConsts, SwerveModuleMk4iL2Consts
# from raptacon3200.utils import sparkMaxUtils

# Third-party imports
import phoenix6
import rev
from wpimath.controller import SimpleMotorFeedforwardMeters
from wpimath.kinematics import SwerveModulePosition, SwerveModuleState
from wpimath.geometry import Rotation2d, Translation2d

"""
This is a basic swerve drive module for a robot running
https://www.swervedrivespecialties.com/products/mk4-swerve-module
with L2 standard and 2 NEO 1.1s
https://www.revrobotics.com/rev-21-1650/
and a
https://store.ctr-electronics.com/cancoder/
Other defaults may be added in future
"""

# sparkMaxUtils stand-in

# Third-party imports
import rev

#############################
# CONSTANTS ###################
#############################


class SparkMaxConstants:
    faultRateMs: int = 50
    motorPosRateMs: int = 50
    appliedOutputRateMs: int = 50
    motorTelmRateMs: int = 50
    analogRateMs: int = 1833
    altEncoderRateMs: int = 1050
    dutyCycleEncRateMs: int = 2150
    dutyCycleEncVelRateMs: int = 3150



def configureSparkMaxCanRates(
    self,
    config: rev.SparkMaxConfig,
    drive_motor_flag: bool,
    faultRateMs: int = SparkMaxConstants.faultRateMs,
    motorPosRateMs: int = SparkMaxConstants.motorPosRateMs,
    appliedOutputRateMs: int = SparkMaxConstants.appliedOutputRateMs
) -> None:
    """
    Configure the data transfer type and rate for swerve drive SparkMaxs. Some configurations
    are universal while others vary based on the given inputs.
    Args:
        config: the configuration object for the SparkMax to update
        drive_motor_flag: if True, the SparkMax controls a drive motor on the swerve drive.
            If False, it controls a steer motor
        faultRateMs: the rate, in milliseconds, at which fault signals are transmitted
        motorPosRateMs: the rate, in milliseconds, at which the position of the motor is transmitted
        appliedOutputRateMs: the rate, in milliseconds, at which the motor's applied output is transmitted
    Returns:
        None - passed configuration is updated in-place
    """
    (
        config.signals
        # Fixed settings
        .absoluteEncoderPositionAlwaysOn(False)
        .absoluteEncoderVelocityAlwaysOn(False)
        .analogPositionAlwaysOn(False)
        .analogVelocityAlwaysOn(False)
        .analogVoltageAlwaysOn(False)
        .externalOrAltEncoderPositionAlwaysOn(False)
        .externalOrAltEncoderVelocityAlwaysOn(False)
        .primaryEncoderPositionAlwaysOn(True)
        .IAccumulationAlwaysOn(False)

        # Input settings
        .primaryEncoderVelocityAlwaysOn(drive_motor_flag)
        .primaryEncoderPositionPeriodMs(motorPosRateMs)
        .appliedOutputPeriodMs(appliedOutputRateMs)
        .faultsPeriodMs(faultRateMs)
    )

# end sparkMaxUtils

class SwerveModuleMk4iSparkMaxNeoCanCoder:
    """
    Module for Mk4i with 2 brushless Falcon 500s and a CANcoder swerve drive
    """
    def __init__(
        self,
        name: str,
        drivetrain_location: Tuple[float, float],
        channel_base: int,
        invert_drive: bool = False,
        invert_steer: bool = False,
        encoder_calibration: float = 0,
        swerve_level_constants: SwerveModuleMk4iConsts=SwerveModuleMk4iL2Consts(),
        update_period: float = 0.05
    ) -> None:
        """
        Creates a new swerve module at a given location in the robot.

        Args:
            name: what the module should be called in any printouts
            drivetrain_location: where the swerve module is located on the drivetrain relative to
                the center of the drivetrain. Units should be in meters. The first coordinate is X (+ front-to-back -),
                the second coordinate is Y (+ left-to-right -)
            channel_base: the root of the CAN IDs for devices in the module. Channels are defined as:
                - channelBase = drive
                - channelBase + 1 = steer
                - channelBase + 2 = absolute encoder
            invert_drive: if True, flip the rotation direction that corresponds to the polarity of the drive motor input.
                We want counter-clockwise rotation when facing the bevel to come from positive polarity
            invert_steer: if True, flip the rotation direction that corresponds to the polarity of the steer motor input.
                We want counter-clockwise rotation when looking down on the top of the robot to come from positive polarity
            encoder_calibration: the starting position of the absolute encoder when the long orientation of the wheel
                follows the X (front-to-back) axis and the bevel faces left
            swerve_level_constants: physical constants that define properties of the swerve module
            update_period: how often, in seconds, to update the feedforward controller on the drive motor
            
        Returns
            None: class initialization executed upon construction
        """
        # Overall instantiation
        self.constants = swerve_level_constants
        setattr(self.constants, "encoder_calibration", encoder_calibration)
        self.name = name
        self.drivetrain_location = Translation2d(*drivetrain_location)

        self.id_lookup = {
            "drive_motor": channel_base,
            "steer_motor": channel_base + 1,
            "absolute_encoder": channel_base + 2
        }

        # Physical device instantiation
        self.drive_motor = rev.SparkMax(self.id_lookup["drive_motor"] , rev.SparkLowLevel.MotorType.kBrushless)
        self.steer_motor = rev.SparkMax(self.id_lookup["steer_motor"], rev.SparkLowLevel.MotorType.kBrushless)
        self.absolute_encoder = phoenix6.hardware.CANcoder(self.id_lookup["absolute_encoder"])

        self.drive_motor_encoder = self.drive_motor.getEncoder()
        self.steer_motor_encoder = self.steer_motor.getEncoder()

        self.drive_motor_pid = self.drive_motor.getClosedLoopController()
        self.drive_motor_feedforward = SimpleMotorFeedforwardMeters(
            kS=0,
            kV=self.constants.kNominalVoltage / self.constants.maxTranslationMPS,
            kA=0,
            dt=update_period
        )
        self.steer_motor_pid = self.steer_motor.getClosedLoopController()

        # Configuration setup
        self.drive_motor_config = rev.SparkMaxConfig()
        self.steer_motor_config = rev.SparkMaxConfig()

        # Absolute encoder configuration
        absolute_encoder_configurator = self.absolute_encoder.configurator
        absolute_encoder_config = phoenix6.configs.CANcoderConfiguration()
        (
            absolute_encoder_config.magnet_sensor
                .with_absolute_sensor_discontinuity_point(1)
                .with_magnet_offset(encoder_calibration)
                .with_sensor_direction(phoenix6.signals.SensorDirectionValue.COUNTER_CLOCKWISE_POSITIVE)
        )

        status = absolute_encoder_configurator.apply(absolute_encoder_config, 0.25)
        if not status.is_ok():
            raise RuntimeError(
                f"Failed to configure CAN encoder on id {self.id_lookup['absolute_encoder']}. Error {status}"
            )

        status = self.absolute_encoder.get_position().set_update_frequency(self.constants.kCanStatusFrameHz, 0.25)
        if not status.is_ok():
            raise RuntimeError(
                f"Failed to configure CAN encoder on id {self.id_lookup['absolute_encoder']}. Error {status}"
            )

        # Steer motor configuration
        self.instantiate_steer_config(invert_steer)
        self.apply_motor_config(to_drive=False, burn_flash=True)

        # Drive motor configuration
        self.instantiate_drive_config(invert_drive)
        self.apply_motor_config(to_drive=True, burn_flash=True)

        # Baseline relative encoders
        self.baseline_relative_encoders()

    def instantiate_steer_config(self, invert: bool) -> None:
        """
        Set a starting configuration for the SparkMax controlling the steer motor. This configuration
        is applied once the robot is turned on and will be held through power cycles unless otherwise updated.

        Args:
            invert: if True, flip the rotation direction that corresponds to the polarity of the steer motor input

        Returns:
            None - internal steer configuration is updated in-place
        """
        self.configureSparkMaxCanRates(self.steer_motor_config, drive_motor_flag=False)
        (
            self.steer_motor_config
            .inverted(invert)
            .setIdleMode(rev.SparkBaseConfig.IdleMode.kCoast)
            .voltageCompensation(self.constants.kNominalVoltage)
            .smartCurrentLimit(self.constants.kSteerCurrentLimit)
            .closedLoopRampRate(self.constants.kRampRate)
            .openLoopRampRate(self.constants.kRampRate)
        )

        (
            self.steer_motor_config.closedLoop
            .setFeedbackSensor(rev.ClosedLoopConfig.FeedbackSensor.kPrimaryEncoder)
            .pid(*OperatorRobotConfig.swerve_steer_pid)
            .positionWrappingEnabled(True)
            .positionWrappingInputRange(0, 360.0)
        )

        (
            self.steer_motor_config.encoder
            .quadratureMeasurementPeriod(self.constants.quadratureMeasurementRateMs)
            .quadratureAverageDepth(self.constants.quadratureAverageDepth)
            .positionConversionFactor(self.constants.steerPositionConversionFactor)
            .velocityConversionFactor(self.constants.steerVelocityConversionFactor)
        )

    def instantiate_drive_config(self, invert: bool) -> None:
        """
        Set a starting configuration for the SparkMax controlling the drive motor. This configuration
        is applied once the robot is turned on and will be held through power cycles unless otherwise updated.

        Args:
            invert: if True, flip the rotation direction that corresponds to the polarity of the drive motor input

        Returns:
            None - internal drive configuration is updated in-place
        """
        self.configureSparkMaxCanRates(self.drive_motor_config, drive_motor_flag=True)
        (
            self.drive_motor_config
            .inverted(invert)
            .setIdleMode(rev.SparkBaseConfig.IdleMode.kBrake)
            .voltageCompensation(self.constants.kNominalVoltage)
            .smartCurrentLimit(self.constants.kDriveCurrentLimit)
            .closedLoopRampRate(self.constants.kRampRate)
            .openLoopRampRate(self.constants.kRampRate)
        )

        (
            self.drive_motor_config.closedLoop
            .setFeedbackSensor(rev.ClosedLoopConfig.FeedbackSensor.kPrimaryEncoder)
            .pidf(*OperatorRobotConfig.swerve_drive_pid)
        )

        (
            self.drive_motor_config.encoder
            .positionConversionFactor(self.constants.drivePositionConversionFactor)
            .velocityConversionFactor(self.constants.driveVelocityConversionFactor)
        )

    def apply_motor_config(self, to_drive: bool, burn_flash: bool = False) -> None:
        """
        Push the current SparkMax configuration to the physical device. After this method is called,
        the target SparkMax will reflect those configuration parameters.

        Args:
            to_drive: if True, push the drive motor's configuration to its SparkMax.
                If False, push the steer motor's configuration to its SparkMax
            burn_flash: if True, the configuration will be saved to memory that survives power cycles.
                If False, the SparkMax will loose these configuration parameters once it looses power.

        Returns:
            None
        """
        motor_set = self.steer_motor
        config_use = self.steer_motor_config
        if to_drive:
            motor_set = self.drive_motor
            config_use = self.drive_motor_config

        write_mode = rev.SparkBase.PersistMode.kNoPersistParameters
        if burn_flash:
            write_mode = rev.SparkBase.PersistMode.kPersistParameters

        motor_set.configure(
            config_use, rev.SparkBase.ResetMode.kNoResetSafeParameters,
            write_mode
        )

    def baseline_relative_encoders(self) -> None:
        """
        "Zero-out" the relative drive and steer relative encoders to ensure the robot starts from a clean slate.
        The drive encoder is set to 0 because the robot is beginning from an origin position. The steer encoder is
        set to the absolute encoder's position to ensure that the relative and absolute encoders are aligned upon
        startup.
        """
        self.drive_motor_encoder.setPosition(0)
        current_absolute_rotation = self.absolute_encoder.get_absolute_position(refresh=True)
        if not current_absolute_rotation.status.is_ok():
            raise RuntimeError("Failed to retrieve starting absolute encoder position baselining relative encoders")
        self.steer_motor_encoder.setPosition((current_absolute_rotation.value_as_double * 360.0) % (360.0))

    def current_raw_absolute_encoder_value(self) -> float | None:
        """
        Get the value from the absolute encoder. When the long orientation of the wheel is perfectly aligned
        with the X (front-to-back) axis and the bevel is facing left, this value should be zero.

        Returns:
            The absolute encoder's value, in fractional rotations with domain [0, 1), if available.
                If not available, return None
        """
        abs_value = self.absolute_encoder.get_absolute_position(refresh=True)
        if abs_value.status.is_ok():
            return abs_value.value_as_double
        return None

    def current_raw_absolute_steer_position(self) -> float:
        """
        Get the value absolute value of the steer motor's rotation position. When the long orientation of
        the wheel is perfectly aligned with the X (front-to-back) axis and the bevel is facing left, this
        value should be zero.

        Returns:
            The steer motor's current absolute rotation position, in degrees with domain [0, 360).
        """
        steer_position = self.current_raw_absolute_encoder_value()
        if steer_position:
            steer_position = steer_position * 360
        else:
            steer_position = self.steer_motor_encoder.getPosition()
        steer_position = steer_position % 360
        return steer_position

    def current_position(self) -> SwerveModulePosition:
        """
        Get the current position of the serve module. Position is defined as how far, in meters, the
        drive motor has driven and the current absolute rotation angle, in degrees, of the steer motor.

        Returns:
            The combined drive and steer position of the module
        """
        drive_position = self.drive_motor_encoder.getPosition()
        steer_position = Rotation2d.fromDegrees(self.current_raw_absolute_steer_position())
        return SwerveModulePosition(drive_position, steer_position)

    def current_state(self) -> SwerveModuleState:
        """
        Get the current state of the serve module. State is defined as the current velocity, in meters per second,
        at which the drive motor is running and the current absolute rotation angle, in degrees, of the steer motor.

        Returns:
            The combined drive and steer state of the module
        """
        current_velocity = self.drive_motor_encoder.getVelocity()
        current_angle = Rotation2d.fromDegrees(self.current_raw_absolute_steer_position())
        return SwerveModuleState(current_velocity, current_angle)

    def set_state(self, state: SwerveModuleState, apply_cosine_scaling: bool = True) -> None:
        """
        Change the state of the swerve module to the given new state, using closed-loop PID control to
        transition from the current state to the new state. This is effectively how we tell our
        drivetrain to drive.

        Args:
            state: the new state the swerve module should immediately transition to
            apply_cosine_scaling: if True, scale the drive speed down according to how perpendicular
                the wheel is to the new state angle. If False, do not scale.

        Returns:
            None - PID controllers are updated in-place with new setpoints
        """
        current_speed = self.current_state().speed

        encoder_rotation = Rotation2d.fromDegrees(self.current_raw_absolute_steer_position())
        state.optimize(encoder_rotation)
        state_degrees = state.angle.degrees()
        state_speed = state.speed

        if apply_cosine_scaling:
            cosine_scaler = (Rotation2d.fromDegrees(state_degrees) - encoder_rotation).cos()
            if cosine_scaler < 0.0:
                cosine_scaler = 1
            state_speed *= cosine_scaler

        self.steer_motor_pid.setReference(state_degrees, rev.SparkLowLevel.ControlType.kPosition, rev.ClosedLoopSlot.kSlot0)
        self.drive_motor_pid.setReference(
            state_speed, rev.SparkLowLevel.ControlType.kVelocity, rev.ClosedLoopSlot.kSlot0,
            self.drive_motor_feedforward.calculate(current_speed, state_speed)
        )

    def set_motor_stop_mode(self, to_drive: bool, to_break: bool) -> None:
        """
        Change whether the target motor should slow down in break or coast mode when told to slow to a stop.
        This is more generally called the idle mode.

        Args:
            to_drive: if True, modify the idle mode for the drive motor.
                If False, modify the idle mode for the steer motor
            to_break: if True, set the idle mode to break (come to a stop as soon as possible).
                If False, set the idel mode to coast (let friction determine when the motor comes to a stop)
        """
        motor_to_set = self.steer_motor_config
        if to_drive:
            motor_to_set = self.drive_motor_config

        stop_mode = rev.SparkBaseConfig.IdleMode.kCoast
        if to_break:
            stop_mode = rev.SparkBaseConfig.IdleMode.kBrake

        motor_to_set.setIdleMode(stop_mode)
