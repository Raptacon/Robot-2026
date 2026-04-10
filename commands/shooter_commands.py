"""Shooter and hood commands."""

import commands2

_SPINUP_RPM = 6000
_SPINUP_HOOD_ANGLE = 0.0


def toggle_spinup(shooter, hood):
    """Toggle flywheel on at 6000 RPM with hood at 0 degrees.

    Uses shooter.flywheelActive as the toggle state. When toggling off,
    RPM is set back to 0.
    """
    def _toggle():
        shooter.toggleFlywheelActive()
        if shooter.flywheelActive:
            shooter.setRPM(_SPINUP_RPM)
            hood.setAngleDegrees(_SPINUP_HOOD_ANGLE)
        else:
            shooter.setRPM(0)

    return commands2.cmd.runOnce(_toggle, shooter, hood)
