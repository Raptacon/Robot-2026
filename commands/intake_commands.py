"""Intake position commands."""

import commands2


def toggle_intake_deploy(intake_position):
    """Return a command that deploys if stowed, or stows if deployed."""
    def _toggle():
        if intake_position.isIntakeDeployed():
            intake_position.stowIntake()
        else:
            intake_position.deployIntake()

    return commands2.cmd.runOnce(_toggle, intake_position)
