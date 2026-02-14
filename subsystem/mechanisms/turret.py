# Native imports
import math

# Third-party imports
import rev
import wpilib
from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
from wpilib.sysid import SysIdRoutineLog


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


class Turret(Subsystem):
    """
    Subsystem for a single-motor turret with position control and soft limits.

    The turret uses a SparkMax motor controller to rotate within defined
    angular boundaries. Position is measured in degrees via the internal
    relative encoder with a configurable conversion factor.
    """

    def __init__(
        self,
        motor: rev.SparkMax,
        position_conversion_factor: float,
        min_soft_limit: float,
        max_soft_limit: float
    ) -> None:
        """
        Creates a new Turret subsystem.

        Args:
            motor: the SparkMax motor controller driving the turret
            position_conversion_factor: encoder conversion factor that converts
                raw encoder rotations to degrees
            min_soft_limit: the minimum turret position in degrees (reverse limit)
            max_soft_limit: the maximum turret position in degrees (forward limit)

        Returns:
            None: class initialization executed upon construction
        """
        super().__init__()
        self.motor = motor
        self.encoder = self.motor.getEncoder()
        self.pid_controller = self.motor.getClosedLoopController()

        self.min_soft_limit = min_soft_limit
        self.max_soft_limit = max_soft_limit

        # Homing and position tracking state
        self._is_homing = False
        self._target_position = None

        config = rev.SparkMaxConfig()

        # General motor settings
        (
            config
            .setIdleMode(rev.SparkBaseConfig.IdleMode.kBrake)
            .voltageCompensation(12.0)
            .smartCurrentLimit(40)
        )

        # Encoder conversion factors
        # Position: rotations -> degrees
        # Velocity: RPM -> degrees/second (divide by 60)
        velocity_conversion_factor = position_conversion_factor / 60.0
        (
            config.encoder
            .positionConversionFactor(position_conversion_factor)
            .velocityConversionFactor(velocity_conversion_factor)
        )

        # Soft limits in degrees
        (
            config.softLimit
            .forwardSoftLimit(max_soft_limit)
            .forwardSoftLimitEnabled(True)
            .reverseSoftLimit(min_soft_limit)
            .reverseSoftLimitEnabled(True)
        )

        # Closed loop feedback sensor
        (
            config.closedLoop
            .setFeedbackSensor(rev.FeedbackSensor.kPrimaryEncoder)
        )

        # Telemetry signals at 20ms
        GetSparkSignalsPositionControlConfig(config.signals, 20)

        # Apply configuration
        self.motor.configure(
            config,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

    def setMotorVoltage(self, output: float) -> None:
        """
        Set the motor voltage directly. Used by SysId routines to drive
        the turret at controlled voltages for characterization.
        Blocked during homing for safety.

        Args:
            output: voltage to apply to the motor

        Returns:
            None
        """
        if self._is_homing:
            return
        self.motor.setVoltage(output)

    def setPosition(self, position_degrees: float) -> None:
        """
        Set the target turret position. The periodic method drives the PID
        controller to this position each cycle. Blocked during homing for safety.

        Args:
            position_degrees: the target turret position in degrees

        Returns:
            None
        """
        if self._is_homing:
            return
        self._target_position = position_degrees

    def getPosition(self) -> float:
        """
        Get the current turret position in degrees.

        Returns:
            The current position of the turret in degrees
        """
        return self.encoder.getPosition()

    def getVelocity(self) -> float:
        """
        Get the current turret angular velocity in degrees per second.

        Returns:
            The current angular velocity of the turret in degrees per second
        """
        return self.encoder.getVelocity()

    @property
    def is_homing(self) -> bool:
        """Whether the turret is currently in a homing routine."""
        return self._is_homing

    def turretDisable(self) -> None:
        """
        Disable turret motor output and clear the target position.
        The turret will idle until a new position is set.

        Returns:
            None
        """
        self._target_position = None
        self.motor.stopMotor()

    def periodic(self) -> None:
        """
        Subsystem periodic method called every cycle by the command scheduler.

        Manages turret state: runs homing routine if active, drives PID to
        target position if set, or idles if disabled.

        Returns:
            None
        """
        if self._is_homing:
            self.homingPeriodic()
        elif self._target_position is not None:
            self.pid_controller.setReference(
                self._target_position,
                rev.SparkLowLevel.ControlType.kPosition,
                rev.ClosedLoopSlot.kSlot0
            )

    def homingInit(
        self,
        max_current: float,
        max_power_pct: float,
        max_homing_time: float,
        homing_forward: bool,
        min_velocity: float = None
    ) -> None:
        """
        Initialize the sensorless homing routine. Saves current motor settings,
        applies homing-specific configuration, and begins the homing process.

        Args:
            max_current: current limit in amps during homing
            max_power_pct: motor duty cycle during homing (0.0-1.0)
            max_homing_time: maximum time in seconds before homing times out
            homing_forward: True to home toward forward limit, False for reverse
            min_velocity: velocity threshold in degrees/second below which the
                turret is considered stalled. Defaults to 5% of turret range
                over 2 seconds.

        Returns:
            None
        """
        if min_velocity is None:
            turret_range = self.max_soft_limit - self.min_soft_limit
            min_velocity = turret_range * 0.05 / 2.0

        # Save current motor settings for restoration
        ca = self.motor.configAccessor
        self._saved_current_limit = ca.getSmartCurrentLimit()
        self._saved_current_free_limit = ca.getSmartCurrentFreeLimit()
        self._saved_current_rpm_limit = ca.getSmartCurrentRPMLimit()
        self._saved_fwd_soft_limit_enabled = (
            ca.softLimit.getForwardSoftLimitEnabled()
        )
        self._saved_rev_soft_limit_enabled = (
            ca.softLimit.getReverseSoftLimitEnabled()
        )

        # Apply homing configuration
        homing_config = rev.SparkMaxConfig()
        homing_config.smartCurrentLimit(int(max_current))
        if homing_forward:
            homing_config.softLimit.forwardSoftLimitEnabled(False)
        else:
            homing_config.softLimit.reverseSoftLimitEnabled(False)

        self.motor.configure(
            homing_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        # Store homing parameters
        self._homing_forward = homing_forward
        self._max_power_pct = max_power_pct
        self._min_velocity = min_velocity
        self._max_homing_time = max_homing_time

        # Set homing state
        self._is_homing = True
        self._target_position = None
        self._stall_detected = False

        # Start timeout timer
        self._homing_timer = wpilib.Timer()
        self._homing_timer.start()

        # Stall detection timer (started when low velocity first detected)
        self._stall_timer = wpilib.Timer()

        # Alerts
        self._homing_status_alert = wpilib.Alert(
            "Turret: homing started", wpilib.Alert.AlertType.kInfo
        )
        self._homing_status_alert.set(True)
        self._homing_error_alert = wpilib.Alert(
            "Turret: homing failed", wpilib.Alert.AlertType.kError
        )
        self._homing_error_alert.set(False)

    def homingPeriodic(self) -> bool:
        """
        Periodic homing logic. Called each cycle by periodic() while homing
        is active. Drives the motor, monitors velocity for stall detection,
        checks limit switches, and handles timeout.

        Returns:
            True when homing is complete (success or failure), False if ongoing
        """
        if not self._is_homing:
            return True

        # Check timeout first
        if self._homing_timer.hasElapsed(self._max_homing_time):
            self._homing_error_alert.setText(
                "Turret: homing failed - timeout"
            )
            self.homingEnd(abort=True)
            return True

        # Check hard limit switch in homing direction
        if self._homing_forward:
            limit_hit = self.motor.getForwardLimitSwitch().get()
        else:
            limit_hit = self.motor.getReverseLimitSwitch().get()

        # Drive motor in homing direction
        if self._homing_forward:
            self.motor.set(self._max_power_pct)
        else:
            self.motor.set(-self._max_power_pct)

        # Check for stall or limit switch
        velocity = abs(self.encoder.getVelocity())

        if limit_hit:
            # Limit switch triggered - homing complete immediately
            home_position = (
                self.max_soft_limit if self._homing_forward
                else self.min_soft_limit
            )
            self.encoder.setPosition(home_position)
            self._homing_status_alert.setText("Turret: homing complete")
            self.homingEnd(abort=False)
            return True

        if velocity < self._min_velocity:
            # Velocity below threshold - start or continue stall timer
            if not self._stall_detected:
                self._stall_detected = True
                self._stall_timer.restart()
            elif self._stall_timer.hasElapsed(0.1):
                # Stalled for 100ms - homing complete
                home_position = (
                    self.max_soft_limit if self._homing_forward
                    else self.min_soft_limit
                )
                self.encoder.setPosition(home_position)
                self._homing_status_alert.setText(
                    "Turret: homing complete"
                )
                self.homingEnd(abort=False)
                return True
        else:
            # Velocity above threshold - reset stall detection
            self._stall_detected = False
            self._stall_timer.stop()
            self._stall_timer.reset()

        return False

    def homingEnd(self, abort: bool) -> None:
        """
        Clean up after homing. Stops the motor, restores saved motor settings,
        and updates alerts. Called on success, failure, or external abort.

        Args:
            abort: True if homing was aborted or failed (encoder not reset),
                False if homing completed successfully

        Returns:
            None
        """
        # Stop motor
        self.motor.stopMotor()

        # Restore saved motor settings
        restore_config = rev.SparkMaxConfig()
        restore_config.smartCurrentLimit(
            int(self._saved_current_limit),
            int(self._saved_current_free_limit),
            int(self._saved_current_rpm_limit)
        )
        (
            restore_config.softLimit
            .forwardSoftLimitEnabled(self._saved_fwd_soft_limit_enabled)
            .reverseSoftLimitEnabled(self._saved_rev_soft_limit_enabled)
        )
        self.motor.configure(
            restore_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        # Clear homing state
        self._is_homing = False

        # Stop timers
        self._homing_timer.stop()
        self._stall_timer.stop()

        # Update alerts
        if abort:
            self._homing_error_alert.setText("Turret: homing aborted")
            self._homing_error_alert.set(True)
            self._homing_status_alert.set(False)
        else:
            self._homing_error_alert.set(False)

    def sysIdLog(self, sys_id_routine: SysIdRoutineLog) -> None:
        """
        Log a frame of data for the turret motor for SysId characterization.

        Records angular position, angular velocity, applied voltage, current,
        motor temperature, and bus voltage. Converts from degrees to radians
        for SysId which expects SI units.

        Args:
            sys_id_routine: the SysIdRoutineLog to record data into

        Returns:
            None
        """
        motor_log = sys_id_routine.motor("turret")

        # Encoder reports in degrees due to conversion factor;
        # SysId expects radians
        angular_position = math.radians(self.encoder.getPosition())
        angular_velocity = math.radians(self.encoder.getVelocity())

        current = self.motor.getOutputCurrent()
        battery_voltage = self.motor.getBusVoltage()
        motor_temp = self.motor.getMotorTemperature()
        applied_voltage = self.motor.getAppliedOutput() * battery_voltage

        motor_log.angularPosition(angular_position)
        motor_log.angularVelocity(angular_velocity)
        motor_log.current(current)
        motor_log.voltage(applied_voltage)
        motor_log.value("temperature", motor_temp, "C")
        motor_log.value("busVoltage", battery_voltage, "V")

    def sysIdQuasistaticCommand(
        self,
        direction: SysIdRoutine.Direction,
        sysIdRoutine: SysIdRoutine
    ) -> Command:
        """
        Create a quasistatic SysId command for the turret.

        Args:
            direction: the direction to run the quasistatic test
            sysIdRoutine: the SysIdRoutine instance to use

        Returns:
            A Command that runs the quasistatic test
        """
        return sysIdRoutine.quasistatic(direction)

    def sysIdDynamicCommand(
        self,
        direction: SysIdRoutine.Direction,
        sysIdRoutine: SysIdRoutine
    ) -> Command:
        """
        Create a dynamic SysId command for the turret.

        Args:
            direction: the direction to run the dynamic test
            sysIdRoutine: the SysIdRoutine instance to use

        Returns:
            A Command that runs the dynamic test
        """
        return sysIdRoutine.dynamic(direction)
