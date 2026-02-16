import commands2
import rev
import wpilib

def setConfig(p: float = 0, i: float = 0, d: float = 0, f: float = 0, inverted: bool = False):
    config = rev.SparkBaseConfig()
    config.inverted(inverted)
    config.closedLoop.pidf(p, i, d, f, rev.ClosedLoopSlot.kSlot0)
    return config

class zShooter():
    def __init__(self):
        super().__init__()
        self.intakeMotor = rev.SparkFlex(14, rev.SparkLowLevel.MotorType.kBrushless)
        self.topMotor = rev.SparkFlex(10, rev.SparkLowLevel.MotorType.kBrushless)
        self.bottomMotor = rev.SparkMax(6, rev.SparkLowLevel.MotorType.kBrushless)
        self.intakeEncoder = self.intakeMotor.getEncoder()
        self.topEncoder = self.topMotor.getEncoder()
        self.bottomEncoder = self.bottomMotor.getEncoder()
        self.pid = self.topMotor.getClosedLoopController()

        self.topMotor.configure(setConfig(), rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)
        self.bottomMotor.configure(setConfig(), rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)
        self.intakeMotor.configure(setConfig(), rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)

    def setIntakeSpeed(self, volts):
        self.intakeMotor.setVoltage(volts)
    def setTopShooterSpeed(self, volts):
        self.topMotor.setVoltage(volts)
    def setBottomShooterSpeed(self, volts):
        self.bottomMotor.setVoltage(volts)