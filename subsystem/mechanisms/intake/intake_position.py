"""Intake position subsystem — servo arm with profiled PID, calibration, and SysId.

Adapted from examples/intake-pos-sysid/intake_pos.py (branch nbeasley-intakePos).

Uses a ProfiledPIDController with trapezoidal motion profile for smooth
velocity-limited position control. Supports two-phase calibration to
discover mechanical hard stops, gravity/static/velocity feedforward,
and SysId characterization routines.
"""

import math

import rev
import wpilib
from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
from ntcore.util import ntproperty
from wpilib.sysid import SysIdRoutineLog
from wpimath.controller import ProfiledPIDController
from wpimath.trajectory import TrapezoidProfile

from constants.swerve_constants import IntakePivotConstants as consts
from utils.position_calibration import PositionCalibration
from utils.spark_max_callbacks import SparkMaxCallbacks
from utils.spark_utils import GetSparkSignalsPositionControlConfig

_NT = f"/subsystems/{consts.name}"


class IntakePosition(Subsystem):
    """Servo-type intake arm with position control and velocity limits."""

    # -- Telemetry --
    nt_position = ntproperty(f"{_NT}/position", 0.0)
    nt_velocity = ntproperty(f"{_NT}/velocity", 0.0)
    nt_applied_output = ntproperty(f"{_NT}/appliedOutput", 0.0)
    nt_current = ntproperty(f"{_NT}/current", 0.0)
    nt_bus_voltage = ntproperty(f"{_NT}/busVoltage", 0.0)
    nt_temperature = ntproperty(f"{_NT}/temperature", 0.0)
    nt_target_position = ntproperty(f"{_NT}/targetPosition", 0.0)
    nt_at_target = ntproperty(f"{_NT}/atTargetPosition", False)
    nt_min_soft_limit = ntproperty(f"{_NT}/minSoftLimit", 0.0)
    nt_max_soft_limit = ntproperty(f"{_NT}/maxSoftLimit", 0.0)
    nt_forward_limit_hit = ntproperty(f"{_NT}/forwardLimitHit", False)
    nt_reverse_limit_hit = ntproperty(f"{_NT}/reverseLimitHit", False)
    nt_is_calibrated = ntproperty(f"{_NT}/isCalibrated", False)

    # -- Tunable motion profile parameters --
    nt_max_velocity = ntproperty(f"{_NT}/pid/maxVelocityDegS", 90.0)
    nt_max_acceleration = ntproperty(f"{_NT}/pid/maxAccelDegS2", 180.0)
    nt_min_output_voltage = ntproperty(f"{_NT}/pid/minOutputVoltage", -4.0)
    nt_max_output_voltage = ntproperty(f"{_NT}/pid/maxOutputVoltage", 4.0)
    nt_kV = ntproperty(f"{_NT}/pid/kV", 4.0 / 90.0)
    nt_kS = ntproperty(f"{_NT}/pid/kS", 0.0)
    nt_kG = ntproperty(f"{_NT}/pid/kG", 0.0)
    nt_arm_zero_angle_deg = ntproperty(f"{_NT}/pid/armZeroAngleDeg", -15.0)

    def __init__(self) -> None:
        super().__init__()

        # Motor setup
        motor_class = getattr(consts, 'motorClass', rev.SparkMax)
        self.motor = motor_class(
            consts.canId,
            rev.SparkLowLevel.MotorType.kBrushless,
        )
        self.encoder = self.motor.getEncoder()
        self.position_conversion_factor = consts.positionConversionFactor

        # Internal state
        self._kS = 0.0
        self._kG = 0.0
        self._kV = 4.0 / 90.0
        self._arm_zero_angle_deg = -15.0
        self._max_velocity = 90.0
        self._max_acceleration = 180.0
        self._min_output_voltage = -4.0
        self._max_output_voltage = 4.0
        self._target_position = None
        self._is_calibrated = False

        # Profiled PID with trapezoidal motion constraints
        self.controller = ProfiledPIDController(
            0.05, 0, 0,
            TrapezoidProfile.Constraints(
                self._max_velocity, self._max_acceleration
            )
        )
        self.controller.setTolerance(1.0, 5.0)
        wpilib.SmartDashboard.putData(
            self.getName() + "/pid", self.controller)

        # Calibration
        self.calibration = self._setup_calibration(
            consts.minSoftLimit, consts.maxSoftLimit)

        # Mechanism2d visualization
        self._configure_mechanism2d()

        # Motor configuration
        cfg = rev.SparkBaseConfig()
        vel_conv = consts.positionConversionFactor / 60.0
        (
            cfg
            .inverted(consts.inverted)
            .setIdleMode(rev.SparkBaseConfig.IdleMode.kBrake)
            .voltageCompensation(12.0)
            .smartCurrentLimit(consts.currentLimitAmps)
        )
        (
            cfg.encoder
            .positionConversionFactor(consts.positionConversionFactor)
            .velocityConversionFactor(vel_conv)
        )
        # Soft limits start disabled so calibration can drive freely
        (
            cfg.softLimit
            .forwardSoftLimit(consts.maxSoftLimit)
            .forwardSoftLimitEnabled(False)
            .reverseSoftLimit(consts.minSoftLimit)
            .reverseSoftLimitEnabled(False)
        )
        GetSparkSignalsPositionControlConfig(cfg.signals, 20)
        self.motor.configure(
            cfg,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kNoPersistParameters,
        )

        self.setName(consts.name)

    def _setup_calibration(
        self, min_soft_limit: float, max_soft_limit: float,
    ) -> PositionCalibration:
        cal = PositionCalibration(
            name=self.getName(),
            fallback_min=min_soft_limit,
            fallback_max=max_soft_limit,
        )
        spark_cbs = SparkMaxCallbacks(self.motor, self.encoder).as_dict()
        cal.set_callbacks(
            set_motor_output=spark_cbs['set_motor_output'],
            stop_motor=spark_cbs['stop_motor'],
            set_position=spark_cbs['set_position'],
            get_velocity=spark_cbs['get_velocity'],
            get_forward_limit_switch=spark_cbs['get_forward_limit_switch'],
            get_reverse_limit_switch=spark_cbs['get_reverse_limit_switch'],
            get_position=spark_cbs['get_position'],
            set_current_limit=spark_cbs['set_current_limit'],
            set_soft_limits=spark_cbs['set_soft_limits'],
            disable_soft_limits=spark_cbs['disable_soft_limits'],
            save_config=spark_cbs['save_config'],
            restore_config=spark_cbs['restore_config'],
        )
        return cal

    def _configure_mechanism2d(self) -> None:
        """Mechanism2d arm visualization.

        display_angle = 90 + encoder_position (CCW sweep as arm deploys).
        """
        self.mech2d = wpilib.Mechanism2d(300, 250)
        pivot = self.mech2d.getRoot("intake_pivot", 200, 80)
        pivot.appendLigament(
            "ref_vertical", 80, 90, 1,
            wpilib.Color8Bit(wpilib.Color.kGray))
        pivot.appendLigament(
            "ref_horizontal", 80, 180, 1,
            wpilib.Color8Bit(wpilib.Color.kGray))
        self.mech_min_limit_arm = pivot.appendLigament(
            "stowed_limit", 80, 90 + consts.minSoftLimit, 4,
            wpilib.Color8Bit(0, 0, 255))
        self.mech_max_limit_arm = pivot.appendLigament(
            "deployed_limit", 80, 90 + consts.maxSoftLimit, 4,
            wpilib.Color8Bit(255, 140, 0))
        self.mech_current_arm = pivot.appendLigament(
            "current", 80, 90 + consts.minSoftLimit, 3,
            wpilib.Color8Bit(wpilib.Color.kRed))
        self.mech_target_arm = pivot.appendLigament(
            "target", 0, 90, 5,
            wpilib.Color8Bit(wpilib.Color.kYellow))
        wpilib.SmartDashboard.putData(
            self.getName() + "/mechanism", self.mech2d)

    # -- Convenience API (preserves old IntakeSubsystem interface) --

    def deployIntake(self) -> None:
        """Move arm to deployed position."""
        self.setPosition(consts.deployedPosition)

    def stowIntake(self) -> None:
        """Move arm to stowed position."""
        self.setPosition(consts.stowedPosition)

    def isIntakeDeployed(self) -> bool:
        """True when arm is at or past the deployed position."""
        return self.encoder.getPosition() >= consts.deployedPosition - 1.0

    def isIntakeStowed(self) -> bool:
        """True when arm is at or before the stowed position."""
        return self.encoder.getPosition() <= consts.stowedPosition + 1.0

    # -- Core API --

    def calibrationInit(
        self,
        max_current: float = 10.0,
        max_power_pct: float = 0.05,
        max_homing_time: float = 10.0,
    ) -> None:
        """Start two-phase calibration at low power."""
        self._is_calibrated = False
        self.calibration.calibration_init(
            max_current=max_current,
            max_power_pct=max_power_pct,
            max_homing_time=max_homing_time,
        )

    def setPosition(self, position_degrees: float) -> None:
        """Set target arm position. Blocked during calibration."""
        if self.calibration.is_busy:
            return
        self._target_position = max(
            self.calibration.min_soft_limit,
            min(self.calibration.max_soft_limit, position_degrees)
        )

    def getPosition(self) -> float:
        return self.encoder.getPosition()

    def getVelocity(self) -> float:
        return self.encoder.getVelocity()

    def disable(self) -> None:
        """Stop arm and clear target."""
        self._target_position = None
        self.motor.stopMotor()

    def setMotorVoltage(self, output: float) -> None:
        """Direct voltage for SysId. Blocked during calibration."""
        if self.calibration.is_busy:
            return
        self.motor.setVoltage(output)

    # -- Periodic --

    def periodic(self) -> None:
        if self.calibration.is_busy:
            self.calibration.periodic()
            if not self.calibration.is_busy:
                self._is_calibrated = self.calibration.is_calibrated
        elif self._target_position is not None:
            position = self.encoder.getPosition()
            pid_output = self.controller.calculate(
                position, self._target_position)

            profile_velocity = self.controller.getSetpoint().velocity

            # Gravity feedforward
            arm_angle_rad = math.radians(
                position + self._arm_zero_angle_deg)
            kG_component = self._kG * math.sin(arm_angle_rad)

            kS_component = (
                self._kS * math.copysign(1.0, profile_velocity)
                if abs(profile_velocity) > 1e-6 else 0.0
            )
            feedforward = (
                kS_component + kG_component
                + self._kV * profile_velocity
            )

            if self.controller.atGoal():
                self.motor.setVoltage(
                    max(self._min_output_voltage,
                        min(self._max_output_voltage, kG_component)))
            else:
                output = max(
                    self._min_output_voltage,
                    min(self._max_output_voltage, pid_output + feedforward))
                self.motor.setVoltage(output)

        self._updateTelemetry()

    def _updateTelemetry(self) -> None:
        self.nt_position = self.encoder.getPosition()
        self.nt_velocity = self.encoder.getVelocity()
        self.nt_applied_output = self.motor.getAppliedOutput()
        self.nt_current = self.motor.getOutputCurrent()
        self.nt_bus_voltage = self.motor.getBusVoltage()
        self.nt_temperature = self.motor.getMotorTemperature()
        self.nt_target_position = (
            self._target_position if self._target_position is not None
            else 0.0)
        self.nt_at_target = (
            self._target_position is not None
            and self.controller.atGoal())
        self.nt_is_calibrated = self._is_calibrated

        sl = self.motor.configAccessor.softLimit
        self.nt_min_soft_limit = sl.getReverseSoftLimit()
        self.nt_max_soft_limit = sl.getForwardSoftLimit()
        self.nt_forward_limit_hit = self.motor.getForwardLimitSwitch().get()
        self.nt_reverse_limit_hit = self.motor.getReverseLimitSwitch().get()

        # Read back live-tunable parameters
        self._min_output_voltage = self.nt_min_output_voltage
        self._max_output_voltage = self.nt_max_output_voltage
        self._kS = self.nt_kS
        self._kG = self.nt_kG
        self._kV = self.nt_kV
        self._arm_zero_angle_deg = self.nt_arm_zero_angle_deg

        new_vel = self.nt_max_velocity
        new_accel = self.nt_max_acceleration
        if new_vel != self._max_velocity or new_accel != self._max_acceleration:
            self._max_velocity = new_vel
            self._max_acceleration = new_accel
            self.controller.setConstraints(
                TrapezoidProfile.Constraints(new_vel, new_accel))

        self.calibration.update_telemetry(self.getName() + "/")

        # Mechanism2d
        self.mech_current_arm.setAngle(90 + self.encoder.getPosition())
        self.mech_min_limit_arm.setAngle(90 + consts.minSoftLimit)
        self.mech_max_limit_arm.setAngle(90 + consts.maxSoftLimit)
        if self._target_position is not None:
            self.mech_target_arm.setLength(80)
            self.mech_target_arm.setAngle(90 + self._target_position)
        else:
            self.mech_target_arm.setLength(0)

    # -- SysId --

    def sysIdLog(self, sys_id_routine: SysIdRoutineLog) -> None:
        motor_log = sys_id_routine.motor("intake_pos")
        angular_position = math.radians(self.encoder.getPosition())
        angular_velocity = math.radians(self.encoder.getVelocity())
        battery_voltage = self.motor.getBusVoltage()
        applied_voltage = self.motor.getAppliedOutput() * battery_voltage
        motor_log.angularPosition(angular_position)
        motor_log.angularVelocity(angular_velocity)
        motor_log.current(self.motor.getOutputCurrent())
        motor_log.voltage(applied_voltage)
        motor_log.value("temperature", self.motor.getMotorTemperature(), "C")
        motor_log.value("busVoltage", battery_voltage, "V")

    def sysIdQuasistaticCommand(
        self, direction: SysIdRoutine.Direction,
        sysIdRoutine: SysIdRoutine,
    ) -> Command:
        return sysIdRoutine.quasistatic(direction)

    def sysIdDynamicCommand(
        self, direction: SysIdRoutine.Direction,
        sysIdRoutine: SysIdRoutine,
    ) -> Command:
        return sysIdRoutine.dynamic(direction)
