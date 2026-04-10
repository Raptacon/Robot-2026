"""Ball transport commands — intake roller, hopper, and feed coordination.

These commands manage the ball path from intake through hopper and feed
into the shooter.
"""

import commands2

import constants.swerve_constants as consts


def run_roller_while_held(intake_roller):
    """Return a startEnd command that runs the intake roller while held."""
    return commands2.cmd.startEnd(
        lambda: intake_roller.setPower(consts.IntakeRollerConstants.defaultPower),
        intake_roller.stop,
        intake_roller,
    )


def run_hopper_and_feed(hopper, feed):
    """Return a command that runs hopper at 50% and feed at 30% while held."""
    def _start():
        hopper.setPower(consts.HopperConstants.defaultPower)
        feed.setPower(0.3)

    def _end():
        hopper.stop()
        feed.stop()

    return commands2.cmd.startEnd(_start, _end, hopper, feed)
