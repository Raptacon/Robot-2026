# Native imports
import math

# Third-party imports
import rev
import wpilib
from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
from ntcore.util import ntproperty
from wpilib.sysid import SysIdRoutineLog
from wpimath.controller import PIDController, ProfiledPIDController
from wpimath.trajectory import TrapezoidProfile

# Internal imports
from utils.position_calibration import PositionCalibration
from utils.spark_max_callbacks import SparkMaxCallbacks


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

    Calibration and homing are delegated to self.calibration
    (PositionCalibration), a reusable controller that discovers mechanical
    limits and persists them across reboots.
    """

    # -- Telemetry (ntproperty) --
    nt_position = ntproperty("/Turret/position", 0.0)
    nt_velocity = ntproperty("/Turret/velocity", 0.0)
    nt_applied_output = ntproperty("/Turret/appliedOutput", 0.0)
    nt_current = ntproperty("/Turret/current", 0.0)
    nt_bus_voltage = ntproperty("/Turret/busVoltage", 0.0)
    nt_temperature = ntproperty("/Turret/temperature", 0.0)
    nt_target_position = ntproperty("/Turret/targetPosition", 0.0)
    nt_at_target = ntproperty("/Turret/atTargetPosition", False)
    nt_min_soft_limit = ntproperty("/Turret/minSoftLimit", 0.0)
    nt_max_soft_limit = ntproperty("/Turret/maxSoftLimit", 0.0)
    nt_forward_limit_hit = ntproperty("/Turret/forwardLimitHit", False)
    nt_reverse_limit_hit = ntproperty("/Turret/reverseLimitHit", False)

    # -- Tunable parameters (read back from NT each cycle) --
    # TODO: Remove ±4V limit after initial hardware testing — restore to ±12V
    nt_min_output_voltage = ntproperty(
        "/Turret/pid/minOutputVoltage", -4.0)
    nt_max_output_voltage = ntproperty(
        "/Turret/pid/maxOutputVoltage", 4.0)
    # Trapezoidal profile constraints (live-tunable)
    nt_max_velocity = ntproperty("/Turret/pid/maxVelocityDegS", 180.0)
    nt_max_acceleration = ntproperty("/Turret/pid/maxAccelDegS2", 360.0)
    # Velocity feedforward: volts per deg/s (kV * profile_velocity = feedforward voltage)
    # Default: 4V at max velocity (4.0 / 180.0 ≈ 0.022)
    nt_kV = ntproperty("/Turret/pid/kV", 4.0 / 180.0)
    # Static friction feedforward: constant voltage to overcome stiction.
    # kS * sign(velocity_command) applied before PID feedback.
    # Default 0.0 = no behavior change until tuned via SysId.
    nt_kS = ntproperty("/Turret/pid/kS", 0.0)

    @classmethod
    def from_config(cls, config) -> "Turret":
        """
        Create a Turret from a TurretConfig object.

        Args:
            config: a TurretConfig instance with turret_motor_can_id,
                position_conversion_factor, min_soft_limit, max_soft_limit

        Returns:
            A configured Turret subsystem
        """
        motor = rev.SparkMax(
            config.turret_motor_can_id,
            rev.SparkLowLevel.MotorType.kBrushless,
        )
        return cls(
            motor=motor,
            position_conversion_factor=config.position_conversion_factor,
            min_soft_limit=config.min_soft_limit,
            max_soft_limit=config.max_soft_limit,
            use_profiled_pid=config.use_profiled_pid,
            kS_voltage=config.kS_voltage,
        )

    def __init__(
        self,
        motor: rev.SparkMax,
        position_conversion_factor: float,
        min_soft_limit: float,
        max_soft_limit: float,
        use_profiled_pid: bool = False,
        kS_voltage: float = 0.0,
    ) -> None:
        """
        Creates a new Turret subsystem.

        Args:
            motor: the SparkMax motor controller driving the turret
            position_conversion_factor: encoder conversion factor that converts
                raw encoder rotations to degrees
            min_soft_limit: the minimum turret position in degrees (reverse limit)
            max_soft_limit: the maximum turret position in degrees (forward limit)
            use_profiled_pid: if True, use ProfiledPIDController with trapezoidal
                ramp-up/down and velocity feedforward. If False, use plain
                PIDController (recommended until hardware is tuned).

        Returns:
            None: class initialization executed upon construction
        """
        super().__init__()
        self.motor = motor
        self.encoder = self.motor.getEncoder()
        self._use_profiled_pid = use_profiled_pid
        self._max_velocity = 180.0    # deg/s
        self._max_acceleration = 360.0  # deg/s²
        self._kV = 4.0 / 180.0
        self._kS = kS_voltage
        if use_profiled_pid:
            self.controller = ProfiledPIDController(
                0.05, 0, 0,
                TrapezoidProfile.Constraints(
                    self._max_velocity, self._max_acceleration)
            )
            self.controller.setTolerance(1.0, 5.0)  # degrees, deg/s
        else:
            self.controller = PIDController(0.05, 0, 0)
            self.controller.setTolerance(1.0)  # degrees
        wpilib.SmartDashboard.putData(
            self.getName() + "/pid", self.controller)

        self.min_soft_limit = min_soft_limit
        self.max_soft_limit = max_soft_limit

        # Voltage output limits (synced from ntproperty each cycle)
        # TODO: Remove ±4V limit after initial hardware testing — restore to ±12V
        self._min_output_voltage = -4.0
        self._max_output_voltage = 4.0

        # Position tracking state
        self._target_position = None

        # Calibration controller (callbacks set up in setupCalibration)
        self.calibration = self.setupCalibration(
            min_soft_limit, max_soft_limit)

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

    def setupCalibration(
        self,
        min_soft_limit: float,
        max_soft_limit: float,
    ) -> PositionCalibration:
        """
        Create and configure the calibration controller for this turret.

        Creates a PositionCalibration with no callbacks, then sets them
        up using set_callbacks(). This keeps __init__ clean and puts all
        the calibration wiring in one place.

        Each callback is a small function that tells PositionCalibration
        how to talk to the motor and encoder. If your mechanism has no
        limit switches, just leave those callbacks out and homing will
        use stall detection instead.

        Args:
            min_soft_limit: the minimum turret position in degrees
            max_soft_limit: the maximum turret position in degrees

        Returns:
            The configured PositionCalibration controller
        """
        # Step 1: Create calibration with no callbacks
        cal = PositionCalibration(
            name=self.getName(),
            fallback_min=min_soft_limit,
            fallback_max=max_soft_limit,
        )

        # Step 2: Build callbacks from the SparkMax motor and encoder.
        # SparkMaxCallbacks generates all the callbacks for you.
        # You can also write your own lambdas instead, for example:
        #     set_motor_output=lambda pct: self.motor.set(pct),
        #     stop_motor=lambda: self.motor.stopMotor(),
        spark_cbs = SparkMaxCallbacks(self.motor, self.encoder).as_dict()

        # Step 3: Set callbacks on the calibration controller.
        # Each callback tells PositionCalibration how to interact
        # with the hardware. See PositionCalibration docs for the
        # full list of available callbacks.
        cal.set_callbacks(
            # --- Core required (must have all three) ---
            # Drive the motor at a duty cycle (-1.0 to 1.0)
            set_motor_output=spark_cbs['set_motor_output'],
            # Stop the motor
            stop_motor=spark_cbs['stop_motor'],
            # Reset the encoder position to a value
            set_position=spark_cbs['set_position'],

            # --- Detection (need at least one per homing direction) ---
            # Read encoder velocity for stall detection
            get_velocity=spark_cbs['get_velocity'],
            # Read limit switches (leave out if not installed)
            get_forward_limit_switch=(
                spark_cbs['get_forward_limit_switch']),
            get_reverse_limit_switch=(
                spark_cbs['get_reverse_limit_switch']),

            # --- Optional (make homing safer but not required) ---
            # Read encoder position (needed for calibration phase 2)
            get_position=spark_cbs['get_position'],
            # Lower current limit during homing to protect the motor
            set_current_limit=spark_cbs['set_current_limit'],
            # Apply soft limits to the motor controller
            set_soft_limits=spark_cbs['set_soft_limits'],
            # Disable soft limits so the motor can travel freely
            disable_soft_limits=spark_cbs['disable_soft_limits'],
            # Save motor config before homing, restore it after
            save_config=spark_cbs['save_config'],
            restore_config=spark_cbs['restore_config'],
        )

        # ---- Shortcut: motor= does the same thing in one line ----
        # If you don't need to customize anything, you can replace
        # all of the above with:
        #
        #     cal = PositionCalibration(
        #         name=self.getName(),
        #         fallback_min=min_soft_limit,
        #         fallback_max=max_soft_limit,
        #         motor=self.motor,
        #         encoder=self.encoder,
        #     )

        return cal

    def setMotorVoltage(self, output: float) -> None:
        """
        Set the motor voltage directly. Used by SysId routines to drive
        the turret at controlled voltages for characterization.
        Blocked during homing/calibration for safety.

        Args:
            output: voltage to apply to the motor

        Returns:
            None
        """
        if self.calibration.is_busy:
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
        if self.calibration.is_busy:
            return
        self._target_position = max(
            self.calibration.min_soft_limit,
            min(self.calibration.max_soft_limit, position_degrees)
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
        return self.calibration.is_homing

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
        self.mech_min_limit_arm = pivot.appendLigament(
            "min_limit", 80, self.min_soft_limit, 2,
            wpilib.Color8Bit(100, 100, 100)
        )
        self.mech_max_limit_arm = pivot.appendLigament(
            "max_limit", 80, self.max_soft_limit, 2,
            wpilib.Color8Bit(100, 100, 100)
        )
        wpilib.SmartDashboard.putData(
            self.getName() + "/mechanism", self.mech2d)

    def periodic(self) -> None:
        """
        Subsystem periodic method called every cycle by the command scheduler.

        Manages turret state: runs calibration/homing routine if active,
        drives PID to target position if set, or idles if disabled.
        Publishes telemetry to SmartDashboard under the subsystem name prefix.

        Returns:
            None
        """
        if self.calibration.is_busy:
            self.calibration.periodic()
        elif self._target_position is not None:
            position = self.encoder.getPosition()
            pid_output = self.controller.calculate(position, self._target_position)
            if self._use_profiled_pid:
                profile_velocity = self.controller.getSetpoint().velocity
                kS_component = (
                    self._kS * math.copysign(1.0, profile_velocity)
                    if abs(profile_velocity) > 1e-6 else 0.0
                )
                feedforward = kS_component + self._kV * profile_velocity
                at_goal = self.controller.atGoal()
            else:
                error = self._target_position - position
                kS_component = (
                    self._kS * math.copysign(1.0, error)
                    if abs(error) > self.controller.getPositionTolerance() else 0.0
                )
                feedforward = kS_component
                at_goal = self.controller.atSetpoint()
            output = max(self._min_output_voltage,
                         min(self._max_output_voltage, pid_output + feedforward))
            if at_goal:
                self.motor.setVoltage(0)
            else:
                self.motor.setVoltage(output)

        self.updateTelemetry()

    def updateTelemetry(self) -> None:
        """
        Publish telemetry via ntproperty and read back tunable
        parameters (voltage limits) for live tuning.
        """
        self.nt_position = self.encoder.getPosition()
        self.nt_velocity = self.encoder.getVelocity()
        self.nt_applied_output = self.motor.getAppliedOutput()
        self.nt_current = self.motor.getOutputCurrent()
        self.nt_bus_voltage = self.motor.getBusVoltage()
        self.nt_temperature = self.motor.getMotorTemperature()
        self.nt_target_position = (
            self._target_position if self._target_position is not None
            else 0.0
        )
        self.nt_at_target = self._target_position is not None

        # Soft limits
        sl = self.motor.configAccessor.softLimit
        self.nt_min_soft_limit = sl.getReverseSoftLimit()
        self.nt_max_soft_limit = sl.getForwardSoftLimit()

        # Limit switches
        self.nt_forward_limit_hit = (
            self.motor.getForwardLimitSwitch().get())
        self.nt_reverse_limit_hit = (
            self.motor.getReverseLimitSwitch().get())

        # Voltage limits (read back from NT for live tuning)
        self._min_output_voltage = self.nt_min_output_voltage
        self._max_output_voltage = self.nt_max_output_voltage

        # Feedforward gains (live-tunable in both modes)
        self._kS = self.nt_kS

        # Profiled-mode-only tuning
        if self._use_profiled_pid:
            self._kV = self.nt_kV
            new_vel = self.nt_max_velocity
            new_accel = self.nt_max_acceleration
            if new_vel != self._max_velocity or new_accel != self._max_acceleration:
                self._max_velocity = new_vel
                self._max_acceleration = new_accel
                self.controller.setConstraints(
                    TrapezoidProfile.Constraints(new_vel, new_accel))

        # Calibration telemetry (delegated)
        prefix = self.getName() + "/"
        self.calibration.update_telemetry(prefix)

        # Mechanism2d visualization
        self.mech_current_arm.setAngle(self.encoder.getPosition())
        self.mech_min_limit_arm.setAngle(self.calibration.min_soft_limit)
        self.mech_max_limit_arm.setAngle(self.calibration.max_soft_limit)
        self.mech_target_arm.setAngle(
            self._target_position if self._target_position is not None
            else 0.0
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
