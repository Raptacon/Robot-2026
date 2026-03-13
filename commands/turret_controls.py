"""
Turret test-mode controls.

Wires controller buttons to turret calibration and position commands.
Intended for use in testInit — not teleop.
"""

import commands2

from subsystem.mechanisms.turret import Turret
from utils.input import InputFactory


# Calibration parameters
_CALIBRATION_CURRENT_LIMIT = 10  # amps
_CALIBRATION_POWER_PCT = 0.15    # 15% power
_CALIBRATION_TIMEOUT = 10        # seconds per phase


def register_test_controls(turret: Turret, factory: InputFactory) -> None:
    """
    Bind turret test-mode buttons from the InputFactory.

    Args:
        turret: the Turret subsystem instance
        factory: the InputFactory with turret actions configured
    """
    # Calibrate: while held runs calibration, on release abort and stop
    calibrate_btn = factory.getButton("turret.calibrate")
    calibrate_btn.onTrue(
        commands2.cmd.runOnce(
            lambda: turret.calibration.calibration_init(
                max_current=_CALIBRATION_CURRENT_LIMIT,
                max_power_pct=_CALIBRATION_POWER_PCT,
                max_homing_time=_CALIBRATION_TIMEOUT,
            ),
            turret,
        )
    )
    calibrate_btn.onFalse(
        commands2.cmd.runOnce(
            lambda: _abort_and_stop(turret),
            turret,
        )
    )

    # Position presets
    factory.getButton("turret.set_30").onTrue(
        commands2.cmd.runOnce(lambda: turret.setPosition(30.0), turret)
    )
    factory.getButton("turret.set_180").onTrue(
        commands2.cmd.runOnce(lambda: turret.setPosition(180.0), turret)
    )
    factory.getButton("turret.set_330").onTrue(
        commands2.cmd.runOnce(lambda: turret.setPosition(330.0), turret)
    )


def _abort_and_stop(turret: Turret) -> None:
    """Abort any active calibration/homing and disable the turret motor."""
    if turret.calibration.is_busy:
        turret.calibration.abort()
    turret.turretDisable()
