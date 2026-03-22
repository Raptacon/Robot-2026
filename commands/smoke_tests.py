from typing import Callable
from constants import SwerveDriveConsts
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from wpimath.geometry import Rotation2d

from wpimath.kinematics import SwerveModuleState

import commands2
import wpilib

class SmokeTests(commands2.SequentialCommandGroup):
    """
    
    
    
    """
    def __init__(self,
                drivetrain: SwerveDrivetrain,
                # velocity_vector_x: Callable[[], float],
                # velocity_vector_y: Callable[[], float],
                # angular_velocity: Callable[[], float]):
    ):
        super().__init__()

        self.drivetrain = drivetrain
        self.progress = False
        self.testMessage = ""
        # self.velocity_vector_x = velocity_vector_x
        # self.velocity_vector_y = velocity_vector_y
        # self.angular_velocity = angular_velocity

        self.addRequirements(self.drivetrain)
        for swerve_module in self.drivetrain.swerve_modules:
            if swerve_module == 0:
                self.addCommands(commands2.cmd.runOnce(self.setMessage(1)))
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            self.addCommands(
                # Current swerve module's drive motor moves forward 0.2 meters per second until driver confirms 
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0.2, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(self.setMessage((swerve_module*6)+2, str(swerve_module.getName()), "Module starts driving")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's drive motor stops
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(self.setMessage((swerve_module*6)+3, str(swerve_module.getName()), "Module stops driving")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 0 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(self.setMessage((swerve_module*6)+4, str(swerve_module.getName()), "Module rotates facing 0 degrees")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 45 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(45)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(self.setMessage((swerve_module*6)+5, str(swerve_module.getName()), "Module rotates facing 45 degrees")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 90 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(90)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(self.setMessage((swerve_module*6)+6, str(swerve_module.getName()), "Module rotates facing 90 degrees")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates back to 0 degrees when finished
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain)
            )

    # def execute(self):
    #     self.drivetrain.swerve_modules[0].set_state(SwerveModuleState(0.2, Rotation2d.fromDegrees(0)))

    def advance(self, progress):
        self.progress = progress

    def setMessage(self, testNumber, testComponent = None, testOutcome = None):
        # self.testMessage = self.allMessages[messageNumber]
        self.testNumber = testNumber
        self.testComponent = testComponent
        self.testOutcome = testOutcome
        if self.testNumber == 1:
            self.testMessage = """1/21:
            \nBeginning of tests. Press start button when expected outcome is satisfied to move onto next test."""
        else:
            self.testMessage = """{self.testNumber}/21:
            \nTesting {self.testComponent}...
            \nEXPECTED OUTCOME: {self.testOutcome}
            """

    def updateMessage(self):
        wpilib.SmartDashboard.putString("Test Message", self.testMessage)
