# Local copy of the turret subsystem for this standalone example.
# The canonical version lives at subsystem/mechanisms/turret.py

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
    """

    def __init__(
        self,
        motor: rev.SparkMax,
        position_conversion_factor: float,
        min_soft_limit: float,
        max_soft_limit: float
    ) -> None:
        super().__init__()
        self.motor = motor
        self.encoder = self.motor.getEncoder()
        self.pid_controller = self.motor.getClosedLoopController()

        self.min_soft_limit = min_soft_limit
        self.max_soft_limit = max_soft_limit

        self._is_homing = False
        self._target_position = None

        config = rev.SparkMaxConfig()

        (
            config
            .setIdleMode(rev.SparkBaseConfig.IdleMode.kBrake)
            .voltageCompensation(12.0)
            .smartCurrentLimit(40)
        )

        velocity_conversion_factor = position_conversion_factor / 60.0
        (
            config.encoder
            .positionConversionFactor(position_conversion_factor)
            .velocityConversionFactor(velocity_conversion_factor)
        )

        (
            config.softLimit
            .forwardSoftLimit(max_soft_limit)
            .forwardSoftLimitEnabled(True)
            .reverseSoftLimit(min_soft_limit)
            .reverseSoftLimitEnabled(True)
        )

        (
            config.closedLoop
            .setFeedbackSensor(rev.FeedbackSensor.kPrimaryEncoder)
        )

        GetSparkSignalsPositionControlConfig(config.signals, 20)

        self.motor.configure(
            config,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

    def setMotorVoltage(self, output: float) -> None:
        if self._is_homing:
            return
        self.motor.setVoltage(output)

    def setPosition(self, position_degrees: float) -> None:
        if self._is_homing:
            return
        self._target_position = position_degrees

    def getPosition(self) -> float:
        return self.encoder.getPosition()

    def getVelocity(self) -> float:
        return self.encoder.getVelocity()

    @property
    def is_homing(self) -> bool:
        return self._is_homing

    def turretDisable(self) -> None:
        self._target_position = None
        self.motor.stopMotor()

    def periodic(self) -> None:
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
        if min_velocity is None:
            turret_range = self.max_soft_limit - self.min_soft_limit
            min_velocity = turret_range * 0.05 / 2.0

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

        self._homing_forward = homing_forward
        self._max_power_pct = max_power_pct
        self._min_velocity = min_velocity
        self._max_homing_time = max_homing_time

        self._is_homing = True
        self._target_position = None
        self._stall_detected = False

        self._homing_timer = wpilib.Timer()
        self._homing_timer.start()

        self._stall_timer = wpilib.Timer()

        self._homing_status_alert = wpilib.Alert(
            "Turret: homing started", wpilib.Alert.AlertType.kInfo
        )
        self._homing_status_alert.set(True)
        self._homing_error_alert = wpilib.Alert(
            "Turret: homing failed", wpilib.Alert.AlertType.kError
        )
        self._homing_error_alert.set(False)

    def homingPeriodic(self) -> bool:
        if not self._is_homing:
            return True

        if self._homing_timer.hasElapsed(self._max_homing_time):
            self._homing_error_alert.setText(
                "Turret: homing failed - timeout"
            )
            self.homingEnd(abort=True)
            return True

        if self._homing_forward:
            limit_hit = self.motor.getForwardLimitSwitch().get()
        else:
            limit_hit = self.motor.getReverseLimitSwitch().get()

        if self._homing_forward:
            self.motor.set(self._max_power_pct)
        else:
            self.motor.set(-self._max_power_pct)

        velocity = abs(self.encoder.getVelocity())

        if limit_hit:
            home_position = (
                self.max_soft_limit if self._homing_forward
                else self.min_soft_limit
            )
            self.encoder.setPosition(home_position)
            self._homing_status_alert.setText("Turret: homing complete")
            self.homingEnd(abort=False)
            return True

        if velocity < self._min_velocity:
            if not self._stall_detected:
                self._stall_detected = True
                self._stall_timer.restart()
            elif self._stall_timer.hasElapsed(0.1):
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
            self._stall_detected = False
            self._stall_timer.stop()
            self._stall_timer.reset()

        return False

    def homingEnd(self, abort: bool) -> None:
        self.motor.stopMotor()

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

        self._is_homing = False

        self._homing_timer.stop()
        self._stall_timer.stop()

        if abort:
            self._homing_error_alert.setText("Turret: homing aborted")
            self._homing_error_alert.set(True)
            self._homing_status_alert.set(False)
        else:
            self._homing_error_alert.set(False)

    def sysIdLog(self, sys_id_routine: SysIdRoutineLog) -> None:
        motor_log = sys_id_routine.motor("turret")

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
        return sysIdRoutine.quasistatic(direction)

    def sysIdDynamicCommand(
        self,
        direction: SysIdRoutine.Direction,
        sysIdRoutine: SysIdRoutine
    ) -> Command:
        return sysIdRoutine.dynamic(direction)
