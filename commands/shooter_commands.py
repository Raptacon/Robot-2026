"""Shooter and hood commands."""

import commands2
from constants.swerve_constants import ShooterConstants


def toggle_spinup(shooter, hood):
    """Toggle flywheel on at configured RPM with hood at 0 degrees.

    Uses shooter.flywheelActive as the toggle state. When toggling off,
    RPM is set back to 0.
    """
    def _toggle():
        shooter.toggleFlywheelActive()
        if shooter.flywheelActive:
            shooter.setRPM(ShooterConstants.fixedRPM)
        else:
            shooter.setRPM(0)

    return commands2.cmd.runOnce(_toggle, shooter, hood)
