# Native imports
import math

# Third-party imports
import rev
import wpilib
from typing import Callable
from commands2 import Command, Subsystem
import commands2.cmd
from commands2.sysid import SysIdRoutine
from ntcore.util import ntproperty
from wpilib.sysid import SysIdRoutineLog
from wpimath.controller import ArmFeedforward, PIDController


def GetSparkSignalsPositionControlConfig(
    signalConfig: rev.SignalsConfig,
    periodMs: int
) -> rev.SignalsConfig:
    """
    Configure telemetry signal frames for a position-controlled SparkMax.

    Enables signals needed for position control and SysId logging:
    bus voltage, applied output, motor temperature, output current,
    primary encoder position, and primary encoder velocity.

    Args:
        signalConfig: the SignalsConfig object to update
        periodMs: the period, in milliseconds, at which signals are transmitted

    Returns:
        The updated SignalsConfig for method chaining
    """
    (
        signalConfig
        .busVoltageAlwaysOn(True)
        .busVoltagePeriodMs(periodMs)
        .appliedOutputAlwaysOn(True)
        .appliedOutputPeriodMs(periodMs)
        .motorTemperatureAlwaysOn(True)
        .motorTemperaturePeriodMs(periodMs)
        .outputCurrentAlwaysOn(True)
        .outputCurrentPeriodMs(periodMs)
        .primaryEncoderPositionAlwaysOn(True)
        .primaryEncoderPositionPeriodMs(periodMs)
        .primaryEncoderVelocityAlwaysOn(True)
        .primaryEncoderVelocityPeriodMs(periodMs)
    )
    return signalConfig


class Hood(Subsystem):
    """
    Subsystem for a hood angle adjustment mechanism.

    Uses a single motor with position control to adjust the shooting angle.
    Position is measured in degrees via the internal relative encoder with
    a configurable conversion factor. Assumes 0 degrees on startup.

    The feedforward uses ArmFeedforward to compensate for gravity —
    0 degrees is approximately horizontal, positive degrees lift
    toward vertical.

    Safety interlock: when enabled (default on code load), the hood
    automatically stows if the injected shooter's RPM setpoint falls
    below a configurable threshold. Safety is always enabled on startup
    and must be explicitly disabled at runtime.
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

    # Safety: persistent configuration
    nt_safety_enabled = ntproperty(
        '/Hood/safetyEnabled', True, writeDefault=True)
    nt_stowed_angle_degrees = ntproperty(
        '/Hood/stowedAngleDegrees', 0.0,
        writeDefault=False, persistent=True)
    nt_safety_rpm_threshold = ntproperty(
        '/Hood/safetyRpmThreshold', 5.0,
        writeDefault=False, persistent=True)

    def __init__(
        self,
        motor: rev.SparkMax,
        position_conversion_factor: float,
        max_angle_degrees: float,
        pid: tuple,
        feedforward: tuple,
        inverted: bool = False,
        min_angle_degrees: float = 0.0,
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
            inverted: whether the motor direction is inverted
            min_angle_degrees: the minimum hood angle in degrees
                (reverse soft limit)
            horizontal_offset_degrees: offset from hood 0-position to
                true horizontal for feedforward calculation
        """
        super().__init__()
        self.motor = motor
        self.encoder = self.motor.getEncoder()

        self.max_angle_degrees = max_angle_degrees
        self.min_angle_degrees = min_angle_degrees
        self._horizontal_offset_degrees = horizontal_offset_degrees

        # Control
        self.controller = PIDController(*pid)
        wpilib.SmartDashboard.putData(
            self.getName() + "/pid", self.controller)
        self.feedforward = ArmFeedforward(*feedforward)

        # Voltage output limits
        self._min_output_volts = -12.0
        self._max_output_volts = 12.0

        # Position tracking
        self._target_degrees = 0.0
        self._enabled = True

        # Configure motor
        config = rev.SparkMaxConfig()
        (
            config
            .inverted(inverted)
            .setIdleMode(rev.SparkBaseConfig.IdleMode.kBrake)
            .voltageCompensation(12.0)
            .smartCurrentLimit(20)
        )

        # Encoder conversion factors
        # position: rotations -> degrees (deg/rotation)
        # velocity: RPM -> deg/s (divide by 60)
        velocity_conversion_factor_dps = position_conversion_factor / 60.0
        (
            config.encoder
            .positionConversionFactor(position_conversion_factor)
            .velocityConversionFactor(velocity_conversion_factor_dps)
        )

        # Soft limits in degrees
        (
            config.softLimit
            .forwardSoftLimit(max_angle_degrees)
            .forwardSoftLimitEnabled(True)
            .reverseSoftLimit(min_angle_degrees)
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

        # Shooter dependency (optional, injected via setShooter)
        self._shooter = None

        # Mechanism2d visualization
        self.configureMechanism2d()

    # -- Setpoint methods --

    def setAngleDegrees(self, degrees: float) -> None:
        """Set hood target angle in degrees, clamped to valid range."""
        if not self._enabled:
            self.enable()
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

    # -- Shooter injection --

    def setShooter(self, shooter) -> None:
        """Inject a shooter subsystem for safety interlock.

        The shooter must have an `RPM` attribute representing
        the current setpoint in RPM.
        """
        self._shooter = shooter

    def getShooter(self):
        """Return the injected shooter, or None."""
        return self._shooter

    # -- Safety --

    def setSafetyEnabled(self, enabled: bool) -> None:
        """Enable or disable the shooter-based safety interlock."""
        self.nt_safety_enabled = enabled

    def getSafetyEnabled(self) -> bool:
        """Return whether the safety interlock is enabled."""
        return self.nt_safety_enabled

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

    def atSetpoint(self) -> bool:
        """Return whether the hood is at its target setpoint."""
        return self.controller.atSetpoint()

    # -- Lifecycle --

    def onDisabledInit(self) -> None:
        """Stop the motor when robot is disabled."""
        self.motor.stopMotor()

    def enable(self) -> None:
        """Re-enable periodic PID control."""
        self.controller.reset()
        self._target_degrees = self.getAngleDegrees()
        self._enabled = True

    def disable(self) -> None:
        """Stop motor output and suspend periodic PID control."""
        self._enabled = False
        self._target_degrees = self.getAngleDegrees()
        self.controller.reset()
        self.motor.stopMotor()

    # -- Periodic --

    def periodic(self) -> None:
        """
        Drive PID + feedforward to target, update viz and telemetry.
        """
        if not self._enabled:
            self.updateTelemetry()
            return

        # Safety interlock: stow hood when shooter setpoint is low
        if (self.nt_safety_enabled
                and self._shooter is not None
                and self._shooter.RPM < self.nt_safety_rpm_threshold):
            self._target_degrees = self.nt_stowed_angle_degrees

        position_deg = self.encoder.getPosition()

        # PID output (volts)
        pid_volts = self.controller.calculate(
            position_deg, self._target_degrees)

        # ArmFeedforward expects angle in radians from horizontal
        ff_angle_rad = math.radians(
            position_deg + self._horizontal_offset_degrees)
        ff_volts = self.feedforward.calculate(ff_angle_rad, 0)

        # Combine and clamp voltage
        total_volts = pid_volts + ff_volts
        total_volts = max(self._min_output_volts,
                          min(self._max_output_volts, total_volts))

        if self.controller.atSetpoint():
            # Still apply feedforward to hold against gravity
            self.motor.setVoltage(ff_volts)
        else:
            self.motor.setVoltage(total_volts)

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
        position_deg = self.encoder.getPosition()
        velocity_dps = self.encoder.getVelocity()

        self.nt_position = position_deg
        self.nt_velocity = velocity_dps
        self.nt_target = self._target_degrees
        self.nt_normalized_position = position_deg / self.max_angle_degrees
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
        self.mech_current_arm.setAngle(position_deg)
        self.mech_target_arm.setAngle(self._target_degrees)

    # -- SysId --

    def setMotorVoltage(self, volts: float) -> None:
        """Set motor voltage directly. Used by SysId routines."""
        self._commanded_volts = volts
        self.motor.setVoltage(volts)

    def sysIdLog(self, sys_id_routine: SysIdRoutineLog) -> None:
        """
        Log a frame of data for SysId characterization.

        Logs radians (SI units for SysId), plus degrees and 0..1
        normalized range as custom fields for analysis.
        """
        motor_log = sys_id_routine.motor("hood")

        position_deg = self.encoder.getPosition()
        velocity_dps = self.encoder.getVelocity()
        position_rad = math.radians(position_deg)
        velocity_rps = math.radians(velocity_dps)

        (
            motor_log
            .angularPosition(position_rad)
            .angularVelocity(velocity_rps)
            .current(self.motor.getOutputCurrent())
            .voltage(getattr(self, '_commanded_volts', 0.0))
            .value("positionDegrees", position_deg, "deg")
            .value("velocityDegPerSec", velocity_dps, "deg/s")
            .value("positionNormalized",
                   position_deg / self.max_angle_degrees, "")
        )

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

    # -- Command generators --

    def autoAngleCommand(self) -> Command:
        """Command that sets hood angle from shooter's distance lookup."""
        def _action():
            if self._shooter is not None:
                self.setAngleDegrees(
                    self._shooter.getHoodAngleForDistance(
                        self._shooter.targetDistance))

        return commands2.cmd.run(_action, self)

    def manualTestCommand(
        self, analog_input: Callable[[], float]
    ) -> Command:
        """Test command: analog input controls hood angle directly.

        Disables safety when input > 0.02, re-enables when released.
        """
        def _action():
            trigger = analog_input()
            self.setSafetyEnabled(trigger <= 0.02)
            self.setAngleNormalized(trigger)

        return commands2.cmd.run(_action, self)
