"""Feed subsystem — manages the upper and lower feed path motors that
push game pieces into the flywheel shooter.

Simple duty-cycle control only (no PID). Each motor is independently
controllable but can be set to the same power for convenience."""

from commands2 import Subsystem
import ntcore
import rev
import wpilib

from constants.swerve_constants import PancakeShooterConstants


class Feed(Subsystem):
    _MECH_WIDTH = 100
    _MECH_HEIGHT = 80
    _MECH_MAX_LENGTH = 40

    def __init__(self):
        super().__init__()
        self._upperPower = 0.0
        self._lowerPower = 0.0

        # Upper feed path motor
        self.upperMotor = rev.SparkMax(
            PancakeShooterConstants.feedUpperMotorId,
            rev.SparkLowLevel.MotorType.kBrushless,
        )
        # Lower feed path motor
        self.lowerMotor = rev.SparkMax(
            PancakeShooterConstants.feedLowerMotorId,
            rev.SparkLowLevel.MotorType.kBrushless,
        )

        self.upperEncoder = self.upperMotor.getEncoder()
        self.lowerEncoder = self.lowerMotor.getEncoder()

        self._configureMotor(
            self.upperMotor,
            PancakeShooterConstants.feedUpperInverted,
        )
        self._configureMotor(
            self.lowerMotor,
            PancakeShooterConstants.feedLowerInverted,
        )

        # NT telemetry under /subsystems/feed/
        table = ntcore.NetworkTableInstance.getDefault().getTable(
            f"subsystems/{PancakeShooterConstants.name}"
        )
        self._nt_upper_power = table.getDoubleTopic("upper_power").publish()
        self._nt_lower_power = table.getDoubleTopic("lower_power").publish()
        self._nt_upper_velocity = table.getDoubleTopic("upper_velocity").publish()
        self._nt_lower_velocity = table.getDoubleTopic("lower_velocity").publish()

        # Mechanism2d with two ligaments for upper/lower motors
        self._mech = wpilib.Mechanism2d(self._MECH_WIDTH, self._MECH_HEIGHT)
        upper_root = self._mech.getRoot("upper", self._MECH_WIDTH / 2, 60)
        self._mech_upper = upper_root.appendLigament(
            "upper_power", 0, 0, 6,
            wpilib.Color8Bit(128, 128, 128)
        )
        lower_root = self._mech.getRoot("lower", self._MECH_WIDTH / 2, 20)
        self._mech_lower = lower_root.appendLigament(
            "lower_power", 0, 0, 6,
            wpilib.Color8Bit(128, 128, 128)
        )
        wpilib.SmartDashboard.putData(
            f"{PancakeShooterConstants.name}/mechanism", self._mech
        )

        self.setName(PancakeShooterConstants.name)

    @staticmethod
    def _configureMotor(motor, invert):
        configs = rev.SparkBaseConfig()
        configs.inverted(invert)
        motor.configure(
            configs,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kPersistParameters,
        )

    # -- public API -----------------------------------------------------------

    def setPower(self, power: float):
        """Set both motors to the same power (-1.0 to 1.0)."""
        self._upperPower = power
        self._lowerPower = power

    def setUpperPower(self, power: float):
        """Set upper feed path motor power (-1.0 to 1.0)."""
        self._upperPower = power

    def setLowerPower(self, power: float):
        """Set lower feed path motor power (-1.0 to 1.0)."""
        self._lowerPower = power

    def stop(self):
        self._upperPower = 0.0
        self._lowerPower = 0.0

    # -- periodic -------------------------------------------------------------

    def periodic(self):
        self.upperMotor.set(self._upperPower)
        self.lowerMotor.set(self._lowerPower)

        self._nt_upper_power.set(self._upperPower)
        self._nt_lower_power.set(self._lowerPower)
        self._nt_upper_velocity.set(self.upperEncoder.getVelocity())
        self._nt_lower_velocity.set(self.lowerEncoder.getVelocity())

        # Update Mechanism2d
        for power, lig in ((self._upperPower, self._mech_upper),
                           (self._lowerPower, self._mech_lower)):
            lig.setLength(abs(power) * self._MECH_MAX_LENGTH)
            if power > 0:
                lig.setColor(wpilib.Color8Bit(wpilib.Color.kGreen))
            elif power < 0:
                lig.setColor(wpilib.Color8Bit(wpilib.Color.kRed))
            else:
                lig.setColor(wpilib.Color8Bit(128, 128, 128))
