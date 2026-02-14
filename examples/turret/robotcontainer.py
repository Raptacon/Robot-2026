#
# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.
#

import commands2
import commands2.button
import commands2.cmd

from subsystems.turretSubsystem import TurretSubsystem


class RobotContainer:
    """
    This class is where the bulk of the robot should be declared. Since Command-based is a
    "declarative" paradigm, very little robot logic should actually be handled in the :class:`.Robot`
    periodic methods (other than the scheduler calls). Instead, the structure of the robot (including
    subsystems, commands, and button mappings) should be declared here.
    """

    def __init__(self) -> None:
        # The robot's subsystems
        self.robot_turret = TurretSubsystem()

        # The driver's controller
        self.driver_controller = commands2.button.CommandXboxController(
            0
        )

        # Configure the button bindings
        self.configureButtonBindings()


    def configureButtonBindings(self) -> None:
        """
        Use this method to define your button->command mappings. Buttons can be created by
        instantiating a :GenericHID or one of its subclasses (Joystick or XboxController),
        and then passing it to a JoystickButton.
        """
        self.driver_controller.a().onTrue(
            commands2.cmd.run(lambda: self.moveTurret(0.5), self.robot_turret)
        )
        self.driver_controller.b().onTrue(
            commands2.cmd.run(lambda: self.moveTurret(-0.5), self.robot_turret)
        )

    def disablePIDSubsystems(self) -> None:
        """Disables all ProfiledPIDSubsystem and PIDSubsystem instances.
        This should be called on robot disable to prevent integral windup."""
        self.robot_turret.disable()

    def getAutonomousCommand(self) -> commands2.Command:
        """Use this to pass the autonomous command to the main {@link Robot} class.

        :returns: the command to run in autonomous
        """
        return commands2.cmd.none()

    def moveTurret(self, rotations: float) -> None:
        self.robot_turret.setGoal(rotations)
        self.robot_turret.enable()