import commands2
import wpilib
import wpimath
from commands2.button import Trigger

from commands.default_swerve_drive import DefaultDrive


def register_controls(drivetrain, container):
    """Wire HID controls for the drivetrain subsystem."""
    driver = container.driver_controller

    # Cancel all commands when left trigger is pulled past halfway
    Trigger(lambda: driver.getLeftTriggerAxis() > 0.5).onTrue(
        commands2.cmd.runOnce(
            lambda: commands2.CommandScheduler.getInstance().cancelAll()
        )
    )

    # Update drivetrain motor idle modes 3s after the robot has been disabled.
    # to_break should be False at competitions where the robot is turned off between matches
    Trigger(wpilib.DriverStation.isDisabled).debounce(3).onTrue(
        commands2.cmd.runOnce(
            drivetrain.set_motor_stop_modes(
                to_drive=True, to_break=True,
                all_motor_override=True, burn_flash=True
            ),
            drivetrain
        )
    )


def teleop_init(drivetrain, container):
    """Called from teleopInit — sets the default drive command."""
    driver = container.driver_controller

    drivetrain.setDefaultCommand(
        DefaultDrive(
            drivetrain,
            lambda: wpimath.applyDeadband(-1 * driver.getLeftY(), 0.06),
            lambda: wpimath.applyDeadband(-1 * driver.getLeftX(), 0.06),
            lambda: wpimath.applyDeadband(-1 * driver.getRightX(), 0.1),
            lambda: not driver.getRightBumperButton()
        )
    )


def teleop_periodic(drivetrain, container):
    """Called from teleopPeriodic."""
    pass
