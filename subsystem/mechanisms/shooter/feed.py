"""Feed subsystem — manages the upper and lower feed path motors that
push game pieces into the flywheel shooter.

Simple duty-cycle control only (no PID). Each motor is independently
controllable but can be set to the same power for convenience."""

from commands2 import Subsystem
import rev
import wpilib

from constants.swerve_constants import PancakeShooterConstants


class Feed(Subsystem):
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

        wpilib.SmartDashboard.putNumber("Feed_Upper_Power", self._upperPower)
        wpilib.SmartDashboard.putNumber("Feed_Lower_Power", self._lowerPower)
        wpilib.SmartDashboard.putNumber("Feed_Upper_Velocity", self.upperEncoder.getVelocity())
        wpilib.SmartDashboard.putNumber("Feed_Lower_Velocity", self.lowerEncoder.getVelocity())
