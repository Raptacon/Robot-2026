import wpilib
import commands2
import rev
import time
import array

from constants import CaptainPlanetConsts as intakeConsts
from config import OperatorRobotConfig


class PositionalIntake(commands2.SubsystemBase):
    def __init__(self):
        self.pivotMotor = rev.SparkFlex(intakeConsts.kIntakeMotorCanId, rev.SparkLowLevel.MotorType.kBrushless)
        self.pivotMotorEncoder = self.pivotMotor.getEncoder()
        self.pivotMotorEncoder.setPosition(0)

        self.rollerMotor = rev.SparkFlex(intakeConsts.kRollerMotorCanId, rev.SparkLowLevel.MotorType.kBrushless)
        self.rollerMotorEncoder = self.rollerMotor.getEncoder()

        self.pivotMotorPID = self.pivotMotor.getClosedLoopController()

        self.configurePivotMotor()

        self.pivotPosition = 0
        self.rollerSpeed = 0

    def configurePivotMotor(self):
        pivotConfig =  rev.SparkMaxConfig()
        (
            pivotConfig.closedLoop
            .setFeedbackSensor(rev.FeedbackSensor.kPrimaryEncoder)
            .pidf(*OperatorRobotConfig.intake_pivot_pid)
        )

        (
            pivotConfig.encoder
            # TODO: find number of rotations from zero to fully deployed, put in denominator
            .positionConversionFactor(1 / 20)
        )

        self.pivotMotor.configure(
            pivotConfig, rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kPersistParameters
        )

    def setPivotPosition(self, pivotPosition: float):
        self.pivotPosition = pivotPosition

    def periodic(self):
        self.pivotMotorPID.setReference(
            self.pivotPosition, rev.SparkLowLevel.ControlType.kPosition, rev.ClosedLoopSlot.kSlot0
        )
        self.rollerMotor.set(self.rollerSpeed)
