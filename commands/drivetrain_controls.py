import commands2
import wpilib
from commands2.button import Trigger

from commands.default_swerve_drive import DefaultDrive


def register_controls(drivetrain, container):
    """Wire HID controls for the drivetrain subsystem.

    Most drive controls (cancel-all, speed toggle, NT sync) are already
    configured in RobotSwerve._configure_controls() via InputFactory.
    This method adds drivetrain-specific triggers that need the subsystem.
    """
    # Update drivetrain motor idle modes 3s after the robot has been disabled.
    # to_break should be False at competitions where the robot is turned off between matches
    Trigger(wpilib.DriverStation.isDisabled).debounce(3).onTrue(
        commands2.cmd.runOnce(
            lambda: drivetrain.set_motor_stop_modes(
                to_drive=True, to_break=True,
                all_motor_override=True, burn_flash=True
            ),
            drivetrain
        )
    )


def teleop_init(drivetrain, container):
    """Called from teleopInit — sets the default drive command."""
    drivetrain.setDefaultCommand(
        DefaultDrive(
            drivetrain,
            container.translate_x,
            container.translate_y,
            container.rotate,
            lambda: not container.robot_relative_btn()
        )
    )


def teleop_periodic(drivetrain, container):
    """Called from teleopPeriodic."""
    pass
