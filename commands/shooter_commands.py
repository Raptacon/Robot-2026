"""Shooter and hood commands."""

import commands2
from constants.swerve_constants import ShooterConstants

_SPINUP_HOOD_ANGLE = 0.0


def toggle_spinup(shooter, hood):
    """Toggle flywheel on at configured RPM with hood at 0 degrees.

    Uses shooter.flywheelActive as the toggle state. When toggling off,
    RPM is set back to 0.
    """
    def _toggle():
        shooter.toggleFlywheelActive()
        print(f"[SPINUP] flywheelActive={shooter.flywheelActive} "
              f"fixedRPM={ShooterConstants.fixedRPM}")
        if shooter.flywheelActive:
            shooter.setRPM(ShooterConstants.fixedRPM)
            print(f"[SPINUP] setRPM({ShooterConstants.fixedRPM}) called, "
                  f"targetRPM={shooter.targetRPM}")
            hood.setAngleDegrees(_SPINUP_HOOD_ANGLE)
        else:
            shooter.setRPM(0)
            print("[SPINUP] setRPM(0) called")

    return commands2.cmd.runOnce(_toggle, shooter, hood)
