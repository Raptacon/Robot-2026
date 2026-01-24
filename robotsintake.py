# Native imports
from typing import Callable

# Internal imports
from subsystem.intakeactions import IntakeSubsystem

# Third-party imports
import commands2
import wpilib
from commands2.button import Trigger

class RobotIntake:
    """
    Container to hold the main robot code
    """

    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        self.intake = IntakeSubsystem()

        self.intakeController = wpilib.XboxController(0)

    def robotPeriodic(self):
        pass

    def disabledInit(self):
        pass

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        pass

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        Trigger(self.intakeController.getYButtonPressed).onTrue(
            commands2.cmd.runOnce(self.intake.stowIntake, self.intake)
        )
        Trigger(self.intakeController.getAButtonPressed).onTrue(
            commands2.cmd.runOnce(self.intake.deployIntake, self.intake)
        )
        Trigger(self.intakeController.getXButtonPressed).onTrue(
            commands2.cmd.runOnce(self.intake.deactivateRoller, self.intake)
        )
        Trigger(self.intakeController.getBButtonPressed).onTrue(
            commands2.cmd.runOnce(self.intake.activateRoller, self.intake)
        )

    def teleopPeriodic(self):
        self.intake.activateRoller()

    def testInit(self):
        pass

    def testPeriodic(self):
        pass
