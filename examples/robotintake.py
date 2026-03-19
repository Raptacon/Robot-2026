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

        wpilib.SmartDashboard.putNumber("Intake Velocity", 0.3)
        wpilib.SmartDashboard.putNumber("Roller Velocity", 0.3)

        self.intakeVelocity = 0
        self.rollerVelocity = 0

    def robotPeriodic(self):
        self.intakeVelocity = wpilib.SmartDashboard.getNumber("Intake Velocity", 0.3)
        self.rollerVelocity = wpilib.SmartDashboard.getNumber("Roller Velocity", 0.3)

        self.intake.updateIntake(self.intakeVelocity)
        self.intake.updateRoller(self.rollerVelocity)

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
            commands2.cmd.run(self.intake.stowIntake, self.intake)
        )
        Trigger(self.intakeController.getAButtonPressed).onTrue(
            commands2.cmd.run(self.intake.deployIntake, self.intake)
        )
        Trigger(self.intakeController.getXButtonPressed).onTrue(
            commands2.cmd.runOnce(self.intake.deactivateRoller, self.intake)
        )
        Trigger(self.intakeController.getBButtonPressed).onTrue(
            commands2.cmd.runOnce(self.intake.activateRoller, self.intake)
        )
        Trigger(self.intakeController.getStartButtonPressed).onTrue(
            commands2.cmd.run(self.intake.rampIntake, self.intake)
        )


    def teleopPeriodic(self):
        pass

    def testInit(self):
        pass

    def testPeriodic(self):
        pass
