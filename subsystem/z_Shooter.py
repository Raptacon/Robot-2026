import commands2
import rev
import wpilib

class zShooter():
    def __init__(self):
        super().__init__()
        self.intakeMotor = rev.SparkFlex(14, rev.SparkLowLevel.MotorType.kBrushless)
        self.topMotor = rev.SparkFlex(10, rev.SparkLowLevel.MotorType.kBrushless)
        self.bottomMotor = rev.SparkMax(6, rev.SparkLowLevel.MotorType.kBrushless)
        self.intakeEncoder = self.intakeMotor.getEncoder()
        self.topEncoder = self.topMotor.getEncoder()
        self.bottomEncoder = self.bottomMotor.getEncoder()
        self.motor_config = rev.SparkBaseConfig()

        self.topMotor.configure(self.motor_config.inverted(False), rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)
        self.bottomMotor.configure(self.motor_config.inverted(False), rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)
        self.intakeMotor.configure(self.motor_config.inverted(False), rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)

    def setIntakeSpeed(self, speed):
        self.intakeMotor.set(speed)
    def setTopShooterSpeed(self, speed):
        self.topMotor.set(speed)
    def setBottomShooterSpeed(self, speed):
        self.bottomMotor.set(speed)