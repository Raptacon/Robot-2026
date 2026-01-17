import commands2
import rev
import wpilib

class zShooter():
    def __init__(self):
        super().__init__()
        self.motor = rev.SparkFlex(1, rev.SparkLowLevel.MotorType.kBrushless)
        self.encoder = self.motor.getEncoder()
        self.motor_config = rev.SparkBaseConfig()

        self.motor_config.inverted(False)
        self.motor.config(self.motor_config, rev.SparkBase.ResetMode.kNoResetSafeParameters, rev.SparkBase.PersistMode.kPersistParameters)

    def setShooterSpeed(self, speed):
        self.motor.set(speed)
