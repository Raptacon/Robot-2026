# Native imports
import math

# Third-party imports
import rev
import wpilib
from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
from wpilib.sysid import SysIdRoutineLog
from wpimath.controller import PIDController


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
        self.controller = PIDController(0, 0, 0)
        wpilib.SmartDashboard.putData(
            self.getName() + "/pid", self.controller)

        self.min_soft_limit = min_soft_limit
        self.max_soft_limit = max_soft_limit

        # Voltage output limits
        self._min_output_voltage = -12.0
        self._max_output_voltage = 12.0

        # Homing and position tracking state
        self._is_homing = False
        self._target_position = None

        # Calibration state
        self._hard_limit_min = None
        self._hard_limit_max = None
        self._is_calibrated = False
        self._is_calibrating = False
        self._calibration_phase = 0
        self._soft_limit_margin = 0.05
        self._position_offset = 0.0

        self.configureMechanism2d()

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
        if self._is_homing or self._is_calibrating:
            return
        self.motor.setVoltage(output)

    def setPosition(self, position_degrees: float) -> None:
        """
        Set the target turret position. The periodic method drives the PID
        controller to this position each cycle. Blocked during homing and
        calibration for safety.

        Args:
            position_degrees: the target turret position in degrees

        Returns:
            None
        """
        if self._is_homing or self._is_calibrating:
            return
        self._target_position = max(
            self.min_soft_limit,
            min(self.max_soft_limit, position_degrees)
        )

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

    def configureMechanism2d(self) -> None:
        """
        Create and publish a Mechanism2d widget for turret visualization.

        Sets up a 2D canvas with:
        - Red arm: current encoder position
        - Green arm: target setpoint position
        - Gray arms: static soft limit indicators

        Returns:
            None
        """
        self.mech2d = wpilib.Mechanism2d(200, 200)
        pivot = self.mech2d.getRoot("turret_pivot", 100, 100)
        self.mech_current_arm = pivot.appendLigament(
            "current_position", 80, 0, 6,
            wpilib.Color8Bit(wpilib.Color.kRed)
        )
        self.mech_target_arm = pivot.appendLigament(
            "target_position", 80, 0, 4,
            wpilib.Color8Bit(wpilib.Color.kGreen)
        )
        pivot.appendLigament(
            "min_limit", 80, self.min_soft_limit, 2,
            wpilib.Color8Bit(100, 100, 100)
        )
        pivot.appendLigament(
            "max_limit", 80, self.max_soft_limit, 2,
            wpilib.Color8Bit(100, 100, 100)
        )
        wpilib.SmartDashboard.putData(
            self.getName() + "/mechanism", self.mech2d)

    def periodic(self) -> None:
        """
        Subsystem periodic method called every cycle by the command scheduler.

        Manages turret state: runs homing routine if active, drives PID to
        target position if set, or idles if disabled. Publishes telemetry
        to SmartDashboard under the subsystem name prefix.

        Returns:
            None
        """
        if self._is_calibrating:
            self.calibrationPeriodic()
        elif self._is_homing:
            self.homingPeriodic()
        elif self._target_position is not None:
            position = self.encoder.getPosition()
            pidOutput = self.controller.calculate(
                position, self._target_position)
            pidOutput = max(self._min_output_voltage,
                           min(self._max_output_voltage, pidOutput))
            if self.controller.atSetpoint():
                self.motor.setVoltage(0)
            else:
                self.motor.setVoltage(pidOutput)

        self.updateTelemetry()

    def updateTelemetry(self) -> None:
        """
        Publish telemetry to SmartDashboard and read back tunable
        parameters (PID gains and voltage limits) for live tuning.
        """
        prefix = self.getName() + "/"
        sd = wpilib.SmartDashboard
        sd.putNumber(prefix + "position", self.encoder.getPosition())
        sd.putNumber(prefix + "velocity", self.encoder.getVelocity())
        sd.putNumber(
            prefix + "appliedOutput", self.motor.getAppliedOutput()
        )
        sd.putNumber(prefix + "current", self.motor.getOutputCurrent())
        sd.putNumber(
            prefix + "busVoltage", self.motor.getBusVoltage()
        )
        sd.putNumber(
            prefix + "temperature", self.motor.getMotorTemperature()
        )
        sd.putBoolean(prefix + "isHoming", self._is_homing)
        target = self._target_position if self._target_position is not None else 0.0
        sd.putNumber(prefix + "targetPosition", target)
        sd.putBoolean(
            prefix + "atTargetPosition",
            self._target_position is not None
        )
        # Soft limits
        sl = self.motor.configAccessor.softLimit
        sd.putNumber(prefix + "minSoftLimit", sl.getReverseSoftLimit())
        sd.putNumber(prefix + "maxSoftLimit", sl.getForwardSoftLimit())
        # Limit switches
        sd.putBoolean(
            prefix + "forwardLimitHit",
            self.motor.getForwardLimitSwitch().get()
        )
        sd.putBoolean(
            prefix + "reverseLimitHit",
            self.motor.getReverseLimitSwitch().get()
        )
        # Voltage output limits (read back from dashboard)
        self._min_output_voltage = sd.getNumber(
            prefix + "pid/minOutputVoltage", self._min_output_voltage)
        self._max_output_voltage = sd.getNumber(
            prefix + "pid/maxOutputVoltage", self._max_output_voltage)
        # Calibration telemetry
        sd.putBoolean(prefix + "isCalibrated", self._is_calibrated)
        sd.putBoolean(prefix + "isCalibrating", self._is_calibrating)
        sd.putNumber(
            prefix + "hardLimitMin",
            self._hard_limit_min if self._hard_limit_min is not None
            else 0.0
        )
        sd.putNumber(
            prefix + "hardLimitMax",
            self._hard_limit_max if self._hard_limit_max is not None
            else 0.0
        )
        sd.putNumber(prefix + "positionOffset", self._position_offset)
        sd.putNumber(prefix + "softLimitMargin", self._soft_limit_margin)
        # Mechanism2d visualization
        self.mech_current_arm.setAngle(self.encoder.getPosition())
        self.mech_target_arm.setAngle(
            self._target_position if self._target_position is not None
            else 0.0
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

    def calibrationInit(
        self,
        max_current: float,
        max_power_pct: float,
        max_homing_time: float,
        min_velocity: float = None,
        known_range: float = None
    ) -> None:
        """
        Start a calibration routine that discovers the turret's mechanical range.

        By default runs two phases:
        Phase 1: Home negative to find the reverse hard limit (set as zero).
        Phase 2: Home positive to find the forward hard limit (measured).

        If known_range is provided, only phase 1 runs. The forward hard limit
        is computed as known_range from the zero point. This is useful when
        only one hard stop is safe to hit.

        After calibration, hard limits are stored and soft limits are
        computed with a configurable safety margin.

        Args:
            max_current: current limit in amps during calibration
            max_power_pct: motor duty cycle during calibration (0.0-1.0)
            max_homing_time: maximum time per phase before timeout
            min_velocity: stall detection threshold in degrees/second
            known_range: if provided, skip phase 2 and use this as the
                full mechanical range in degrees from the zero point

        Returns:
            None
        """
        # Save motor settings for restoration after calibration
        ca = self.motor.configAccessor
        self._cal_saved_current_limit = ca.getSmartCurrentLimit()
        self._cal_saved_current_free_limit = ca.getSmartCurrentFreeLimit()
        self._cal_saved_current_rpm_limit = ca.getSmartCurrentRPMLimit()
        self._cal_saved_fwd_soft_limit_enabled = (
            ca.softLimit.getForwardSoftLimitEnabled()
        )
        self._cal_saved_rev_soft_limit_enabled = (
            ca.softLimit.getReverseSoftLimitEnabled()
        )
        self._cal_saved_fwd_soft_limit = ca.softLimit.getForwardSoftLimit()
        self._cal_saved_rev_soft_limit = ca.softLimit.getReverseSoftLimit()

        # Disable both soft limits for free travel
        disable_config = rev.SparkMaxConfig()
        (
            disable_config.softLimit
            .forwardSoftLimitEnabled(False)
            .reverseSoftLimitEnabled(False)
        )
        self.motor.configure(
            disable_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        # Store calibration parameters for phase transitions
        self._cal_max_current = max_current
        self._cal_max_power_pct = max_power_pct
        self._cal_max_homing_time = max_homing_time
        self._cal_min_velocity = min_velocity
        self._cal_known_range = known_range

        self._is_calibrating = True
        self._calibration_phase = 1
        self._target_position = None

        # Start phase 1: home negative
        self.homingInit(
            max_current, max_power_pct, max_homing_time,
            homing_forward=False, min_velocity=min_velocity
        )

        self._cal_status_alert = wpilib.Alert(
            "Turret: calibration phase 1 - homing negative",
            wpilib.Alert.AlertType.kInfo
        )
        self._cal_status_alert.set(True)

    def calibrationPeriodic(self) -> None:
        """
        Periodic calibration logic. Manages the two-phase calibration
        state machine. Called by periodic() when calibrating.

        Returns:
            None
        """
        if not self._is_calibrating:
            return

        if self._calibration_phase == 1:
            done = self.homingPeriodic()
            if done:
                if not self._is_homing:
                    # Phase 1 complete - set encoder to 0
                    self.encoder.setPosition(0.0)
                    self._hard_limit_min = 0.0

                    if self._cal_known_range is not None:
                        # Single-direction: use known range
                        self._hard_limit_max = self._cal_known_range
                        self.calibrationEnd(abort=False)
                    else:
                        # Two-phase: start phase 2
                        self._cal_status_alert.setText(
                            "Turret: calibration phase 2 - homing positive"
                        )
                        self._calibration_phase = 2
                        self.homingInit(
                            self._cal_max_current,
                            self._cal_max_power_pct,
                            self._cal_max_homing_time,
                            homing_forward=True,
                            min_velocity=self._cal_min_velocity
                        )
                else:
                    # Homing failed (timeout) - abort calibration
                    self.calibrationEnd(abort=True)

        elif self._calibration_phase == 2:
            # Save position before homingPeriodic may reset it
            measured_position = self.encoder.getPosition()
            done = self.homingPeriodic()
            if done:
                if not self._is_homing:
                    # Phase 2 complete - record max position
                    self._hard_limit_max = measured_position
                    self.calibrationEnd(abort=False)
                else:
                    # Homing failed - abort
                    self.calibrationEnd(abort=True)

    def calibrationEnd(self, abort: bool) -> None:
        """
        Clean up after calibration. Restores motor settings and, on
        success, computes and applies soft limits.

        Args:
            abort: True if calibration failed, False on success

        Returns:
            None
        """
        self.motor.stopMotor()
        self._is_calibrating = False
        self._calibration_phase = 0
        self._is_homing = False

        if not abort and self._hard_limit_max is not None:
            self._is_calibrated = True
            self._cal_status_alert.setText(
                "Turret: calibration complete"
            )
            # Apply soft limits with margin
            self.setSoftLimitMargin(self._soft_limit_margin)
        else:
            # Restore original soft limits on abort
            restore_config = rev.SparkMaxConfig()
            restore_config.smartCurrentLimit(
                int(self._cal_saved_current_limit),
                int(self._cal_saved_current_free_limit),
                int(self._cal_saved_current_rpm_limit)
            )
            (
                restore_config.softLimit
                .forwardSoftLimit(self._cal_saved_fwd_soft_limit)
                .forwardSoftLimitEnabled(
                    self._cal_saved_fwd_soft_limit_enabled)
                .reverseSoftLimit(self._cal_saved_rev_soft_limit)
                .reverseSoftLimitEnabled(
                    self._cal_saved_rev_soft_limit_enabled)
            )
            self.motor.configure(
                restore_config,
                rev.ResetMode.kNoResetSafeParameters,
                rev.PersistMode.kNoPersistParameters
            )
            self._cal_status_alert.setText(
                "Turret: calibration aborted"
            )

    def setSoftLimitMargin(self, margin_pct: float) -> None:
        """
        Set the soft limit safety margin as a percentage of the full
        calibrated range and apply to the motor controller.

        Args:
            margin_pct: safety margin as a fraction (e.g. 0.05 for 5%)

        Returns:
            None
        """
        if not self._is_calibrated:
            return
        self._soft_limit_margin = margin_pct
        full_range = self._hard_limit_max - self._hard_limit_min
        margin = full_range * margin_pct
        self.min_soft_limit = self._hard_limit_min + margin
        self.max_soft_limit = self._hard_limit_max - margin

        limit_config = rev.SparkMaxConfig()
        (
            limit_config.softLimit
            .forwardSoftLimit(self.max_soft_limit)
            .forwardSoftLimitEnabled(True)
            .reverseSoftLimit(self.min_soft_limit)
            .reverseSoftLimitEnabled(True)
        )
        self.motor.configure(
            limit_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

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
