# Native imports
import math

# Third-party imports
import rev
import wpilib
from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
from ntcore.util import ntproperty
from wpilib.sysid import SysIdRoutineLog
from wpimath.controller import ArmFeedforward, PIDController

# Internal imports
from subsystem.mechanisms.turret import GetSparkSignalsPositionControlConfig


class Hood(Subsystem):
    """
    Subsystem for a hood angle adjustment mechanism.

    Uses a single motor with position control to adjust the shooting angle.
    Position is measured in degrees via the internal relative encoder with
    a configurable conversion factor. Assumes 0 degrees on startup.

    The feedforward uses ArmFeedforward to compensate for gravity —
    0 degrees is approximately horizontal, positive degrees lift
    toward vertical.
    """

    # Telemetry via ntproperty (published to NT, not persisted)
    nt_position = ntproperty('/Hood/position', 0.0, writeDefault=True)
    nt_velocity = ntproperty('/Hood/velocity', 0.0, writeDefault=True)
    nt_target = ntproperty('/Hood/targetPosition', 0.0, writeDefault=True)
    nt_normalized_position = ntproperty(
        '/Hood/normalizedPosition', 0.0, writeDefault=True)
    nt_normalized_target = ntproperty(
        '/Hood/normalizedTarget', 0.0, writeDefault=True)
    nt_at_setpoint = ntproperty(
        '/Hood/atSetpoint', False, writeDefault=True)
    nt_applied_output = ntproperty(
        '/Hood/appliedOutput', 0.0, writeDefault=True)
    nt_current = ntproperty('/Hood/current', 0.0, writeDefault=True)
    nt_bus_voltage = ntproperty(
        '/Hood/busVoltage', 0.0, writeDefault=True)
    nt_min_soft_limit = ntproperty(
        '/Hood/minSoftLimit', 0.0, writeDefault=True)
    nt_max_soft_limit = ntproperty(
        '/Hood/maxSoftLimit', 0.0, writeDefault=True)

    def __init__(
        self,
        motor: rev.SparkMax,
        position_conversion_factor: float,
        max_angle_degrees: float,
        pid: tuple,
        feedforward: tuple,
        horizontal_offset_degrees: float = 0.0,
    ) -> None:
        """
        Creates a new Hood subsystem.

        Args:
            motor: the SparkMax motor controller driving the hood
            position_conversion_factor: encoder conversion factor that
                converts raw encoder rotations to degrees
            max_angle_degrees: the maximum hood angle in degrees
                (forward soft limit)
            pid: (P, I, D) gains for the WPILib PIDController
            feedforward: (kS, kG, kV, kA) gains for ArmFeedforward
            horizontal_offset_degrees: offset from hood 0-position to
                true horizontal for feedforward calculation
        """
        super().__init__()
        self.motor = motor
        self.encoder = self.motor.getEncoder()

        self.max_angle_degrees = max_angle_degrees
        self.min_angle_degrees = 0.0
        self._horizontal_offset_degrees = horizontal_offset_degrees

        # Control
        self.controller = PIDController(*pid)
        wpilib.SmartDashboard.putData(
            self.getName() + "/pid", self.controller)
        self.feedforward = ArmFeedforward(*feedforward)

        # Voltage output limits
        self._min_output_voltage = -12.0
        self._max_output_voltage = 12.0

        # Position tracking
        self._target_degrees = 0.0

        # Configure motor
        config = rev.SparkMaxConfig()
        (
            config
            .setIdleMode(rev.SparkBaseConfig.IdleMode.kBrake)
            .voltageCompensation(12.0)
            .smartCurrentLimit(20)
        )

        # Encoder conversion factors
        velocity_conversion_factor = position_conversion_factor / 60.0
        (
            config.encoder
            .positionConversionFactor(position_conversion_factor)
            .velocityConversionFactor(velocity_conversion_factor)
        )

        # Soft limits in degrees
        (
            config.softLimit
            .forwardSoftLimit(max_angle_degrees)
            .forwardSoftLimitEnabled(True)
            .reverseSoftLimit(0.0)
            .reverseSoftLimitEnabled(True)
        )

        # Telemetry signals at 20ms
        GetSparkSignalsPositionControlConfig(config.signals, 20)

        # Apply configuration
        self.motor.configure(
            config,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        # Assume 0 position on startup
        self.encoder.setPosition(0)

        # Mechanism2d visualization
        self.configureMechanism2d()

    # -- Setpoint methods --

    def setAngleDegrees(self, degrees: float) -> None:
        """Set hood target angle in degrees, clamped to valid range."""
        self._target_degrees = max(
            self.min_angle_degrees,
            min(self.max_angle_degrees, degrees)
        )

    def setAngleNormalized(self, value: float) -> None:
        """Set hood target from 0..1 range (0 = min, 1 = max angle)."""
        value = max(0.0, min(1.0, value))
        self._target_degrees = value * self.max_angle_degrees

    def setAngleRadians(self, radians: float) -> None:
        """Set hood target angle in radians, converted to degrees."""
        self.setAngleDegrees(math.degrees(radians))

    # -- Getter methods --

    def getAngleDegrees(self) -> float:
        """Get current hood angle in degrees from encoder."""
        return self.encoder.getPosition()

    def getAngleNormalized(self) -> float:
        """Get current hood angle as 0..1 normalized value."""
        return self.encoder.getPosition() / self.max_angle_degrees

    def getAngleRadians(self) -> float:
        """Get current hood angle in radians."""
        return math.radians(self.encoder.getPosition())

    def getTargetDegrees(self) -> float:
        """Get the current target angle in degrees."""
        return self._target_degrees

    def atSetpoint(self, tolerance_deg: float = 0.5) -> bool:
        """Check if the hood is within tolerance of the target."""
        return abs(self.getAngleDegrees() - self._target_degrees) < tolerance_deg

    # -- Lifecycle --

    def onDisabledInit(self) -> None:
        """Stop the motor when robot is disabled."""
        self.motor.stopMotor()

    def disable(self) -> None:
        """Stop motor output and hold current position as target."""
        self._target_degrees = self.getAngleDegrees()
        self.motor.stopMotor()

    # -- Periodic --

    def periodic(self) -> None:
        """
        Drive PID + feedforward to target, update viz and telemetry.
        """
        position = self.encoder.getPosition()

        # PID output
        pid_output = self.controller.calculate(
            position, self._target_degrees)

        # ArmFeedforward expects angle in radians from horizontal
        ff_angle_rad = math.radians(
            position + self._horizontal_offset_degrees)
        ff_output = self.feedforward.calculate(ff_angle_rad, 0)

        # Combine and clamp voltage
        total_voltage = pid_output + ff_output
        total_voltage = max(self._min_output_voltage,
                           min(self._max_output_voltage, total_voltage))

        if self.controller.atSetpoint():
            # Still apply feedforward to hold against gravity
            self.motor.setVoltage(ff_output)
        else:
            self.motor.setVoltage(total_voltage)

        self.updateTelemetry()

    # -- Mechanism2d --

    def configureMechanism2d(self) -> None:
        """
        Create and publish a Mechanism2d widget for hood visualization.

        Sets up a 2D canvas with:
        - Red arm: current encoder position
        - Green arm: target setpoint position
        - Gray arms: static soft limit indicators
        """
        self.mech2d = wpilib.Mechanism2d(200, 200)
        pivot = self.mech2d.getRoot("hood_pivot", 100, 100)
        self.mech_current_arm = pivot.appendLigament(
            "current_position", 80, 0, 6,
            wpilib.Color8Bit(wpilib.Color.kRed)
        )
        self.mech_target_arm = pivot.appendLigament(
            "target_position", 80, 0, 4,
            wpilib.Color8Bit(wpilib.Color.kGreen)
        )
        pivot.appendLigament(
            "min_limit", 80, self.min_angle_degrees, 2,
            wpilib.Color8Bit(100, 100, 100)
        )
        pivot.appendLigament(
            "max_limit", 80, self.max_angle_degrees, 2,
            wpilib.Color8Bit(100, 100, 100)
        )
        wpilib.SmartDashboard.putData(
            self.getName() + "/mechanism", self.mech2d)

    # -- Telemetry --

    def updateTelemetry(self) -> None:
        """Publish telemetry via ntproperty and update Mechanism2d."""
        position = self.encoder.getPosition()

        self.nt_position = position
        self.nt_velocity = self.encoder.getVelocity()
        self.nt_target = self._target_degrees
        self.nt_normalized_position = position / self.max_angle_degrees
        self.nt_normalized_target = (
            self._target_degrees / self.max_angle_degrees)
        self.nt_at_setpoint = self.atSetpoint()
        self.nt_applied_output = self.motor.getAppliedOutput()
        self.nt_current = self.motor.getOutputCurrent()
        self.nt_bus_voltage = self.motor.getBusVoltage()

        # Soft limits
        sl = self.motor.configAccessor.softLimit
        self.nt_min_soft_limit = sl.getReverseSoftLimit()
        self.nt_max_soft_limit = sl.getForwardSoftLimit()

        # Update mechanism2d arms
        self.mech_current_arm.setAngle(position)
        self.mech_target_arm.setAngle(self._target_degrees)

    # -- SysId --

    def setMotorVoltage(self, voltage: float) -> None:
        """Set motor voltage directly. Used by SysId routines."""
        self.motor.setVoltage(voltage)

    def sysIdLog(self, sys_id_routine: SysIdRoutineLog) -> None:
        """
        Log a frame of data for SysId characterization.

        Converts from degrees to radians for SysId (expects SI units).
        """
        motor_log = sys_id_routine.motor("hood")

        angular_position = math.radians(self.encoder.getPosition())
        angular_velocity = math.radians(self.encoder.getVelocity())

        current = self.motor.getOutputCurrent()
        battery_voltage = self.motor.getBusVoltage()
        applied_voltage = self.motor.getAppliedOutput() * battery_voltage

        motor_log.angularPosition(angular_position)
        motor_log.angularVelocity(angular_velocity)
        motor_log.current(current)
        motor_log.voltage(applied_voltage)
        motor_log.value("busVoltage", battery_voltage, "V")

    def sysIdQuasistaticCommand(
        self,
        direction: SysIdRoutine.Direction,
        sysIdRoutine: SysIdRoutine
    ) -> Command:
        """Create a quasistatic SysId command for the hood."""
        return sysIdRoutine.quasistatic(direction)

    def sysIdDynamicCommand(
        self,
        direction: SysIdRoutine.Direction,
        sysIdRoutine: SysIdRoutine
    ) -> Command:
        """Create a dynamic SysId command for the hood."""
        return sysIdRoutine.dynamic(direction)


def createHood(constants, config) -> Hood:
    """
    Factory helper to create a Hood subsystem from config objects.

    Args:
        constants: HoodConstants (motorId, positionConversionFactor,
            maxAngleDegrees, inverted)
        config: HoodConfig (hoodPID, hoodFeedforward,
            horizontalOffsetDegrees)

    Returns:
        A fully configured Hood subsystem
    """
    motor = rev.SparkMax(
        constants.motorId,
        rev.SparkLowLevel.MotorType.kBrushless
    )
    return Hood(
        motor=motor,
        position_conversion_factor=constants.positionConversionFactor,
        max_angle_degrees=constants.maxAngleDegrees,
        pid=config.hoodPID,
        feedforward=config.hoodFeedforward,
        horizontal_offset_degrees=config.horizontalOffsetDegrees,
    )
