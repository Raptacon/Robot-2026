# Native imports
import math

# Third-party imports
import rev
import wpilib
from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
from ntcore.util import ntproperty
from wpilib.sysid import SysIdRoutineLog
from wpimath.controller import ProfiledPIDController
from wpimath.trajectory import TrapezoidProfile

# Internal imports — adjust path if running from project root
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from utils.position_calibration import PositionCalibration
from utils.spark_max_callbacks import SparkMaxCallbacks


def GetSparkSignalsPositionControlConfig(
    signalConfig: rev.SignalsConfig,
    periodMs: int
) -> rev.SignalsConfig:
    """Configure telemetry frames for a position-controlled SparkMax."""
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


class IntakePos(Subsystem):
    """
    Subsystem for a servo-type intake arm with position control and velocity limits.

    Uses a SparkMax motor (CAN ID 20) to rotate the intake arm within defined
    angular boundaries. Position is measured in degrees via the internal
    relative encoder with a configurable conversion factor.

    Motion is velocity-limited via ProfiledPIDController with a trapezoidal
    profile so the arm ramps up and down smoothly without slamming into limits.

    Calibration is performed at low power (5%) to safely discover mechanical
    hard stops, then soft limits are set from those discovered positions.
    SysId routines allow characterization of kS and kV feedforward gains.
    """

    # -- Telemetry (ntproperty) --
    nt_position = ntproperty("/IntakePos/position", 0.0)
    nt_velocity = ntproperty("/IntakePos/velocity", 0.0)
    nt_applied_output = ntproperty("/IntakePos/appliedOutput", 0.0)
    nt_current = ntproperty("/IntakePos/current", 0.0)
    nt_bus_voltage = ntproperty("/IntakePos/busVoltage", 0.0)
    nt_temperature = ntproperty("/IntakePos/temperature", 0.0)
    nt_target_position = ntproperty("/IntakePos/targetPosition", 0.0)
    nt_at_target = ntproperty("/IntakePos/atTargetPosition", False)
    nt_min_soft_limit = ntproperty("/IntakePos/minSoftLimit", 0.0)
    nt_max_soft_limit = ntproperty("/IntakePos/maxSoftLimit", 0.0)
    nt_forward_limit_hit = ntproperty("/IntakePos/forwardLimitHit", False)
    nt_reverse_limit_hit = ntproperty("/IntakePos/reverseLimitHit", False)
    nt_is_calibrated = ntproperty("/IntakePos/isCalibrated", False)

    # -- Tunable motion profile parameters (live via NT) --
    # Maximum arm velocity in degrees/second
    nt_max_velocity = ntproperty("/IntakePos/pid/maxVelocityDegS", 90.0)
    # Maximum arm acceleration in degrees/second^2
    nt_max_acceleration = ntproperty("/IntakePos/pid/maxAccelDegS2", 180.0)
    # Voltage output clamp — start conservative, expand after testing
    nt_min_output_voltage = ntproperty("/IntakePos/pid/minOutputVoltage", -4.0)
    nt_max_output_voltage = ntproperty("/IntakePos/pid/maxOutputVoltage", 4.0)
    # Velocity feedforward: volts per deg/s.  Tune via SysId dynamic test.
    # Default: 4V at max velocity (4.0 / 90.0 ≈ 0.044)
    nt_kV = ntproperty("/IntakePos/pid/kV", 4.0 / 90.0)
    # Static friction feedforward. Start at 0.0; tune via SysId quasistatic.
    nt_kS = ntproperty("/IntakePos/pid/kS", 0.0)
    # Gravity feedforward: volts to hold the arm horizontal against gravity.
    # Applied as kG * sin(arm_angle_rad) every cycle — even when holding position.
    # 0° = vertical (straight down), 90° = horizontal.
    # Tune via SysId quasistatic (measure stall voltage at 90° from vertical).
    nt_kG = ntproperty("/IntakePos/pid/kG", 0.0)
    # Arm angle at encoder zero (degrees from vertical, 0 = straight down).
    # After calibration the encoder is zeroed at the reverse hard stop.
    # Set this to the physical angle of the stowed hard stop relative to vertical.
    # Stowed hard stop is ~15° past vertical → -15.0
    nt_arm_zero_angle_deg = ntproperty("/IntakePos/pid/armZeroAngleDeg", -15.0)

    def __init__(
        self,
        motor: rev.SparkMax,
        position_conversion_factor: float,
        min_soft_limit: float,
        max_soft_limit: float,
        kS_voltage: float = 0.0,
    ) -> None:
        """
        Create a new IntakePos subsystem.

        Args:
            motor: SparkMax motor controller on CAN ID 20
            position_conversion_factor: converts motor rotations to arm degrees
            min_soft_limit: minimum arm angle in degrees (stowed/hard stop side)
            max_soft_limit: maximum arm angle in degrees (deployed/hard stop side)
            kS_voltage: static friction feedforward in volts. Start at 0.0 and
                tune via SysId quasistatic after characterization.
        """
        super().__init__()
        self.motor = motor
        self.encoder = self.motor.getEncoder()
        self.position_conversion_factor = position_conversion_factor
        self.min_soft_limit = min_soft_limit
        self.max_soft_limit = max_soft_limit
        self._kS = kS_voltage
        self._kG = 0.0
        self._kV = 4.0 / 90.0
        self._arm_zero_angle_deg = 0.0
        self._max_velocity = 90.0     # deg/s
        self._max_acceleration = 180.0  # deg/s²
        self._min_output_voltage = -4.0
        self._max_output_voltage = 4.0

        # Velocity-limited position control via trapezoidal profiled PID.
        # This is the primary "velocity limits for control" mechanism:
        # the controller never commands velocity above nt_max_velocity.
        self.controller = ProfiledPIDController(
            0.05, 0, 0,
            TrapezoidProfile.Constraints(
                self._max_velocity, self._max_acceleration
            )
        )
        self.controller.setTolerance(1.0, 5.0)  # degrees, deg/s
        wpilib.SmartDashboard.putData(self.getName() + "/pid", self.controller)

        self._target_position = None
        self._is_calibrated = False

        # Calibration
        self.calibration = self._setup_calibration(min_soft_limit, max_soft_limit)

        # Mechanism2d visualization
        self._configure_mechanism2d()

        # Configure motor
        cfg = rev.SparkMaxConfig()
        velocity_conversion_factor = position_conversion_factor / 60.0
        (
            cfg
            .setIdleMode(rev.SparkBaseConfig.IdleMode.kBrake)
            .voltageCompensation(12.0)
            .smartCurrentLimit(40)
        )
        (
            cfg.encoder
            .positionConversionFactor(position_conversion_factor)
            .velocityConversionFactor(velocity_conversion_factor)
        )
        # Soft limits start DISABLED so calibration can drive freely past them.
        # The calibration set_soft_limits callback enables them with the
        # discovered hard-stop positions after homing completes.
        (
            cfg.softLimit
            .forwardSoftLimit(max_soft_limit)
            .forwardSoftLimitEnabled(False)
            .reverseSoftLimit(min_soft_limit)
            .reverseSoftLimitEnabled(False)
        )
        GetSparkSignalsPositionControlConfig(cfg.signals, 20)
        self.motor.configure(
            cfg,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kNoPersistParameters,
        )

    def _setup_calibration(
        self,
        min_soft_limit: float,
        max_soft_limit: float,
    ) -> PositionCalibration:
        """Wire PositionCalibration callbacks to the SparkMax motor."""
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
        """Publish a Mechanism2d widget for intake arm visualization.

        Coordinate mapping: our arm uses 0 = vertical (straight up in display),
        but Mechanism2d uses 0 = horizontal-right.  We apply a +90° offset
        so our 0° displays as pointing straight up:
          arm   0° → mech2d  90° (pointing straight up)
          arm -15° → mech2d  75° (slightly past straight up, stowed)
          arm  90° → mech2d 180° (deployed, pointing left/outward)
        Pivot is placed near the bottom of the canvas so the arm swings up.
        """
        self.mech2d = wpilib.Mechanism2d(200, 200)
        # Pivot near bottom-center; arm swings upward
        pivot = self.mech2d.getRoot("intake_pivot", 100, 30)
        self.mech_current_arm = pivot.appendLigament(
            "current_position", 80, 90, 6,
            wpilib.Color8Bit(wpilib.Color.kRed)
        )
        self.mech_target_arm = pivot.appendLigament(
            "target_position", 80, 90, 4,
            wpilib.Color8Bit(wpilib.Color.kGreen)
        )
        self.mech_min_limit_arm = pivot.appendLigament(
            "min_limit", 80, self.min_soft_limit + 90, 2,
            wpilib.Color8Bit(100, 100, 100)
        )
        self.mech_max_limit_arm = pivot.appendLigament(
            "max_limit", 80, self.max_soft_limit + 90, 2,
            wpilib.Color8Bit(100, 100, 100)
        )
        wpilib.SmartDashboard.putData(
            self.getName() + "/mechanism", self.mech2d)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def calibrationInit(
        self,
        max_current: float = 10.0,
        max_power_pct: float = 0.05,
        max_homing_time: float = 10.0,
    ) -> None:
        """
        Start a two-phase calibration routine at 5% motor power.

        Phase 1 drives toward the reverse hard stop (stowed), sets that as
        zero.  Phase 2 drives toward the forward hard stop (deployed) and
        measures the full range.  Soft limits are applied once done.

        Args:
            max_current: current limit in amps during homing (default 10A)
            max_power_pct: motor duty cycle fraction (default 0.05 = 5%)
            max_homing_time: seconds per phase before timeout (default 10s)
        """
        self._is_calibrated = False
        self.calibration.calibration_init(
            max_current=max_current,
            max_power_pct=max_power_pct,
            max_homing_time=max_homing_time,
        )

    def setPosition(self, position_degrees: float) -> None:
        """
        Set the target arm position. Blocked during calibration.

        Args:
            position_degrees: desired arm angle in degrees
        """
        if self.calibration.is_busy:
            return
        self._target_position = max(
            self.calibration.min_soft_limit,
            min(self.calibration.max_soft_limit, position_degrees)
        )

    def getPosition(self) -> float:
        """Return current arm angle in degrees."""
        return self.encoder.getPosition()

    def getVelocity(self) -> float:
        """Return current arm velocity in degrees per second."""
        return self.encoder.getVelocity()

    def disable(self) -> None:
        """Stop the arm and clear the target position."""
        self._target_position = None
        self.motor.stopMotor()

    def setMotorVoltage(self, output: float) -> None:
        """
        Apply a direct voltage to the motor. Used by SysId routines.
        Blocked during calibration.

        Args:
            output: voltage in volts
        """
        if self.calibration.is_busy:
            return
        self.motor.setVoltage(output)

    # -------------------------------------------------------------------------
    # Subsystem lifecycle
    # -------------------------------------------------------------------------

    def periodic(self) -> None:
        """
        Called every 20 ms by the command scheduler.

        Runs calibration if active, otherwise drives the profiled PID toward
        the target position with kS/kV feedforward.
        """
        if self.calibration.is_busy:
            self.calibration.periodic()
            if not self.calibration.is_busy:
                # Calibration just finished
                self._is_calibrated = True
        elif self._target_position is not None:
            position = self.encoder.getPosition()
            pid_output = self.controller.calculate(position, self._target_position)

            profile_velocity = self.controller.getSetpoint().velocity

            # Gravity feedforward: kG * sin(θ), always active (holds arm at rest too).
            # θ is measured from vertical (0 = straight down, 90 = horizontal).
            arm_angle_rad = math.radians(position + self._arm_zero_angle_deg)
            kG_component = self._kG * math.sin(arm_angle_rad)

            kS_component = (
                self._kS * math.copysign(1.0, profile_velocity)
                if abs(profile_velocity) > 1e-6 else 0.0
            )
            feedforward = kS_component + kG_component + self._kV * profile_velocity

            if self.controller.atGoal():
                # Still apply gravity feedforward to hold position against gravity
                self.motor.setVoltage(
                    max(self._min_output_voltage,
                        min(self._max_output_voltage, kG_component))
                )
            else:
                output = max(
                    self._min_output_voltage,
                    min(self._max_output_voltage, pid_output + feedforward)
                )
                self.motor.setVoltage(output)

        self.updateTelemetry()

    def updateTelemetry(self) -> None:
        """Publish sensor data and read back live-tunable parameters from NT."""
        self.nt_position = self.encoder.getPosition()
        self.nt_velocity = self.encoder.getVelocity()
        self.nt_applied_output = self.motor.getAppliedOutput()
        self.nt_current = self.motor.getOutputCurrent()
        self.nt_bus_voltage = self.motor.getBusVoltage()
        self.nt_temperature = self.motor.getMotorTemperature()
        self.nt_target_position = (
            self._target_position if self._target_position is not None else 0.0
        )
        self.nt_at_target = (
            self._target_position is not None and self.controller.atGoal()
        )
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

        # Calibration telemetry
        self.calibration.update_telemetry(self.getName() + "/")

        # Mechanism2d — apply +90° offset so our 0° (vertical) = mech2d 90° (up)
        self.mech_current_arm.setAngle(self.encoder.getPosition() + 90)
        self.mech_min_limit_arm.setAngle(self.calibration.min_soft_limit + 90)
        self.mech_max_limit_arm.setAngle(self.calibration.max_soft_limit + 90)
        self.mech_target_arm.setAngle(
            (self._target_position + 90) if self._target_position is not None
            else 90
        )

    # -------------------------------------------------------------------------
    # SysId
    # -------------------------------------------------------------------------

    def sysIdLog(self, sys_id_routine: SysIdRoutineLog) -> None:
        """
        Log a frame of SysId characterization data for the intake arm.

        Converts degrees -> radians for SysId (expects SI units).

        Args:
            sys_id_routine: the SysIdRoutineLog to record into
        """
        motor_log = sys_id_routine.motor("intake_pos")

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
        sysIdRoutine: SysIdRoutine,
    ) -> Command:
        """Return a quasistatic SysId command for the given direction."""
        return sysIdRoutine.quasistatic(direction)

    def sysIdDynamicCommand(
        self,
        direction: SysIdRoutine.Direction,
        sysIdRoutine: SysIdRoutine,
    ) -> Command:
        """Return a dynamic SysId command for the given direction."""
        return sysIdRoutine.dynamic(direction)
