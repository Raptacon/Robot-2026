import commands2
import rev

class BallPitHopper(commands2.SubsystemBase):
    def __init__(self) -> None:
        self.intakeMotor = rev.SparkMax(21, rev.SparkLowLevel.MotorType.kBrushless)

    def runHexShaft(self, percent : float):
        self.intakeMotor.set(percent)
