import rev
from commands2 import Command, Subsystem
from wpilib.drive import DifferentialDrive
from typing import Callable

kLeftMotorID = 10
kRightMotorID = 11


class Drivetrain(Subsystem):
    def __init__(self, leftConfig: rev.SparkBaseConfig, rightConfig: rev.SparkBaseConfig):
        super().__init__()
        self.left_motor = rev.SparkMax(kLeftMotorID, rev.SparkLowLevel.MotorType.kBrushless)
        self.left_motor.configure(leftConfig, rev.ResetMode.kResetSafeParameters, rev.PersistMode.kNoPersistParameters)

        self.right_motor = rev.SparkMax(kRightMotorID, rev.SparkLowLevel.MotorType.kBrushless)
        self.right_motor.configure(rightConfig, rev.ResetMode.kResetSafeParameters, rev.PersistMode.kNoPersistParameters)

        self.drive = DifferentialDrive(self.left_motor, self.right_motor)

    def arcadeDriveCommand(self, fwd: Callable[[], float], rot: Callable[[], float]) -> Command:
        return self.run(lambda: self.drive.arcadeDrive(fwd(), rot()))
