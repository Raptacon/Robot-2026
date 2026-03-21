from typing import Callable
from constants import SwerveDriveConsts
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from wpimath.geometry import Rotation2d

from wpimath.kinematics import SwerveModuleState

import commands2

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
        # self.velocity_vector_x = velocity_vector_x
        # self.velocity_vector_y = velocity_vector_y
        # self.angular_velocity = angular_velocity

        self.addRequirements(self.drivetrain)
        for swerve_module in self.drivetrain.swerve_modules:
            self.addCommands(
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's drive motor moves forward 0.2 meters per second until driver confirms 
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0.2, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's drive motor stops
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 0 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 45 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(45)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 90 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(90)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates back to 0 degrees when finished
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain)
            )

    # def execute(self):
    #     self.drivetrain.swerve_modules[0].set_state(SwerveModuleState(0.2, Rotation2d.fromDegrees(0)))

    def advance(self, progress):
        self.progress = progress
