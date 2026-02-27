# Native imports
import math

# Third-party imports
import rev
import wpilib
from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
from wpilib.sysid import SysIdRoutineLog
from wpimath.controller import PIDController

# Internal imports
from utils.position_calibration import PositionCalibration


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

        # Position tracking state
        self._target_position = None

        # Calibration controller
        self.calibration = PositionCalibration(
            name=self.getName(),
            motor=self.motor,
            encoder=self.encoder,
            default_min_soft_limit=min_soft_limit,
            default_max_soft_limit=max_soft_limit,
        )

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
        # Calibration telemetry (delegated)
        self.calibration.update_telemetry(prefix)
        # Mechanism2d visualization
        self.mech_current_arm.setAngle(self.encoder.getPosition())
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
