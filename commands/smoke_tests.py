from typing import Callable
from constants import SwerveDriveConsts
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from wpimath.geometry import Rotation2d
# from subsystem.mechanisms.turret import Turret
from subsystem.intakeactions import IntakeSubsystem
from subsystem.ballpit import BallPitHopper
from subsystem.shooter import Shooter

from wpimath.kinematics import SwerveModuleState

import commands2
import wpilib

class SmokeTests(commands2.SequentialCommandGroup):
    """    
    
    """
    def __init__(self,
                drivetrain: SwerveDrivetrain,
                # velocity_vector_x: Callable[[], float]),
                # velocity_vector_y: Callable[[], float],
                # angular_velocity: Callable[[], float],
                # turret: Turret,
                intake: IntakeSubsystem,
                hopper: BallPitHopper,
                shooter: Shooter
                ):
        super().__init__()

        self.drivetrain = drivetrain
        # self.turret = turret
        self.intake = intake
        self.hopper = hopper
        self.shooter = shooter

        self.progress = False
        self.testMessage = ""
        self.totaltests = 24
        # self.velocity_vector_x = velocity_vector_x
        # self.velocity_vector_y = velocity_vector_y
        # self.angular_velocity = angular_velocity

        self.addRequirements(self.drivetrain)
        # Tests Swerve Modules (0-20)
        for index, swerve_module in enumerate(self.drivetrain.swerve_modules):
            if index == 0:
                self.addCommands(
                    commands2.cmd.runOnce(lambda: self.setMessage(0)),
                    commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)))
            self.addCommands(
                # Current swerve module's drive motor moves forward 0.2 meters per second until driver confirms 
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0.2, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda index=index, swerve_module=swerve_module:self.setMessage((index*5)+1, str(swerve_module.getName()), "Check to see if module starts driving...", "Manual Confirmation")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's drive motor stops
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda index=index, swerve_module=swerve_module:self.setMessage((index*5)+2, str(swerve_module.getName()), "Check to see if module stops driving...", "Manual Confirmation")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 0 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda index=index, swerve_module=swerve_module:self.setMessage((index*5)+3, str(swerve_module.getName()), "Check to see if module rotates facing 0 degrees...", "Manual Confirmation")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 45 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(45)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda index=index, swerve_module=swerve_module:self.setMessage((index*5)+4, str(swerve_module.getName()), "Check to see if module rotates facing 45 degrees...", "Manual Confirmation")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 90 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(90)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda index=index, swerve_module=swerve_module:self.setMessage((index*5)+5, str(swerve_module.getName()), "Check to see if module rotates facing 90 degrees...", "Manual Confirmation")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates back to 0 degrees when finished
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain)
            )
        # self.addRequirements(turret)
        self.addRequirements(intake)
        # Test Onboard Sensors (21-24)
        self.addCommands(
            # Test confirms after Feed sensor activation
            # commands2.runOnce(lambda: self.setMessage(21, "Onboard Sensors", "Trigger Breakbeam Sensors at Feed", "Successful Activation of Feed Breakbeam Sensors")),
            # commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            # Test confirms after Intake sensor activation
            commands2.cmd.runOnce(lambda: self.setMessage(22, "Onboard Sensors", "Trigger Hall-Effects Sensor at Intake", "Successful Activation of Intake Hall-Effects Sensor")),
            commands2.WaitUntilCommand(lambda: intake.HallEffectSensor.get()),
            # Test confirms after Turret sensor activation
            # commands2.runOnce(lambda: self.setMessage(23, "Onboard Sensors", "Trigger Forward Hall-Effects Sensor at Turret", "Successful Activation of Turret Forward Hall-Effects Sensor")),
            # commands2.WaitUntilCommand(lambda: turret.motor.getForwardLimitSwitch().get()),
            # commands2.runOnce(lambda: self.setMessage(24, "Onboard Sensors", "Trigger Reverse Hall-Effects Sensor at Turret", "Successful Activation of Turret Reverse Hall-Effects Sensor")),
            # commands2.WaitUntilCommand(lambda: turret.motor.getReverseLimitSwitch().get()),
        )
        # Test Components (25-)
        self.addCommands(
            #Test Intake Deployment
            commands2.InstantCommand(lambda intake=intake: intake.deployIntake(), self.intake),
            commands2.cmd.runOnce(self.setMessage(25, "Intake", "Check to see if Intake begins deploying...", "Manual Confirmation")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Intake Stow
            commands2.InstantCommand(lambda intake=intake: intake.stowIntake(), self.intake),
            commands2.cmd.runOnce(self.setMessage(26, "Intake", "Check to see if Intake begins stowing...", "Manual Confirmation")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Hopper Activation
            commands2.InstantCommand(lambda hopper=hopper: hopper.setHexShaftSpeed(0.2), self.hopper),
            commands2.cmd.runOnce(self.setMessage(27, "Hopper", "Check to see if Hopper activates...", "Manual Confirmation")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Hopper Deactivation
            commands2.InstantCommand(lambda hopper=hopper: hopper.zeroHopperVelocity(), self.hopper),
            commands2.cmd.runOnce(self.setMessage(28, "Hopper", "Check to see if Hopper deactivates...", "Manual Confirmation")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Shooter Feed Activation
            commands2.InstantCommand(lambda shooter=shooter: shooter.toggleFeedActive(), self.shooter),
            commands2.cmd.runOnce(self.setMessage(29, "Shooter", "Check to see if Feed activates...", "Manual Confirmation")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Shooter Feed Deactivation
            commands2.InstantCommand(lambda shooter=shooter: shooter.toggleFeedActive(), self.shooter),
            commands2.cmd.runOnce(self.setMessage(30, "Shooter", "Check to see if Feed deactivates...", "Manual Confirmation")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Shooter Flywheel Activation
            commands2.InstantCommand(lambda shooter=shooter: shooter.setRPM(3000), self.shooter),
            commands2.cmd.runOnce(self.setMessage(31, "Shooter", "Check to see if BOTH Flywheels activate...", "Manual Confirmation")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Shooter Flywheel Deactivation
            commands2.InstantCommand(lambda shooter=shooter: shooter.setRPM(0), self.shooter),
            commands2.cmd.runOnce(self.setMessage(32, "Shooter", "Check to see if BOTH Flywheels deactivate...", "Manual Confirmation")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
        )

    # def execute(self):
    #     self.drivetrain.swerve_modules[0].set_state(SwerveModuleState(0.2, Rotation2d.fromDegrees(0)))

    def advance(self, progress = True):
        self.progress = progress


    def setMessage(self, testNumber, testComponent = None, testInstruction = None, testConfirmation = None):
        # self.testMessage = self.allMessages[messageNumber]
        self.testNumber = testNumber
        self.testComponent = testComponent
        self.testInstruction = testInstruction
        self.testConfirmation = testConfirmation
        if self.testNumber == 0:
            self.testMessage = F"""{self.testNumber}/{self.totaltests}:\nBeginning of tests.
            \nPress start button when expected outcome is satisfied to move onto next test."""
        else:
            self.testMessage = F"""{self.testNumber}/{self.totaltests}:\nTesting {self.testComponent}...
            \nDRIVER INSTRUCTION: {self.testInstruction}
            \nTEST CONFIRMATION: {self.testConfirmation}
            """

    def updateMessage(self):
        wpilib.SmartDashboard.putString("Test Message", self.testMessage)