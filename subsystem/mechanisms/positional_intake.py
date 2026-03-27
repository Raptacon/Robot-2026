import wpilib
import commands2
import rev
import time
import array

from constants import CaptainPlanetConsts as intakeConsts
from config import OperatorRobotConfig


class PositionalIntake(commands2.SubsystemBase):
    def __init__(self):
        self.pivotMotor = rev.SparkFlex(intakeConsts.kPivotMotorCanId, rev.SparkLowLevel.MotorType.kBrushless)
        self.pivotMotorEncoder = self.pivotMotor.getEncoder()
        self.pivotMotorEncoder.setPosition(0)

        self.rollerMotor = rev.SparkFlex(intakeConsts.kRollerMotorCanId, rev.SparkLowLevel.MotorType.kBrushless)
        self.rollerMotorEncoder = self.rollerMotor.getEncoder()

        self.pivotMotorPID = self.pivotMotor.getClosedLoopController()

        self.configurePivotMotor(intakeConsts.kInvertPivot, intakeConsts.kPivotCurrentLimitAmps)
        self.configureRollerMotor(intakeConsts.kInvertRoller, intakeConsts.kRollerCurrentLimitAmps)

        self.pivotPosition = 0
        self.rollerSpeed = 0

    def configurePivotMotor(self, invert: bool, currentLimit: float):
        pivotConfig =  rev.SparkFlexConfig()
        (
            pivotConfig.inverted(invert)
            .smartCurrentLimit(freeLimit=)
        )

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

    def configureRollerMotor(self, invert: bool, currentLimit: float):
        rollerConfig =  rev.SparkFlexConfig()

        (
            rollerConfig.inverted(invert)
            .smartCurrentLimit(freeLimit=)
        )

        self.pivotMotor.configure(
            rollerConfig, rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kPersistParameters
        )


    def setPivotPosition(self, pivotPosition: float):
        self.pivotPosition = pivotPosition

    def setRollerSpeed(self, rollerSpeed: float):
        self.rollerSpeed = rollerSpeed

    def stopMotors(self):
        self.pivotMotor.stopMotor()
        self.rollerMotor.stopMotor()

    def periodic(self):
        self.pivotMotorPID.setReference(
            self.pivotPosition, rev.SparkLowLevel.ControlType.kPosition, rev.ClosedLoopSlot.kSlot0
        )
        self.rollerMotor.set(self.rollerSpeed)
