"""Hopper subsystem — single motor, duty-cycle control."""

from commands2 import Subsystem
import rev
import wpilib

from constants.swerve_constants import HopperConstants


class Hopper(Subsystem):
    def __init__(self):
        super().__init__()
        self._power = 0.0

        self.motor = rev.SparkMax(
            HopperConstants.canId,
            rev.SparkLowLevel.MotorType.kBrushless,
        )

        config = rev.SparkBaseConfig()
        config.inverted(HopperConstants.inverted)
        self.motor.configure(
            config,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kPersistParameters,
        )

        self.encoder = self.motor.getEncoder()

    def setPower(self, power: float):
        """Set motor power (-1.0 to 1.0 duty cycle)."""
        self._power = power

    def stop(self):
        """Set motor power to zero."""
        self._power = 0.0

    def getPower(self) -> float:
        """Return last commanded power."""
        return self._power

    def periodic(self):
        self.motor.set(self._power)
        wpilib.SmartDashboard.putNumber("Hopper_Power", self._power)
        wpilib.SmartDashboard.putNumber("Hopper_Velocity", self.encoder.getVelocity())
