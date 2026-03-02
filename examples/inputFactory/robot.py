#!/usr/bin/env python3
"""InputFactory Example — Swerve drive with config-driven controls.

Demonstrates how to use InputFactory to replace hardcoded
XboxController calls with config-driven managed inputs.

Features shown:
  - ManagedAnalog for drive axes (deadband, inversion, scale from YAML)
  - ManagedButton.bind() for auto-binding using configured trigger modes
  - Drivetrain subsystem with default command and swappable axes
  - get_factory() for subsystem-local input access (LED fetches its own rumble)
  - factory.update() in robotPeriodic for NT sync and rumble timeouts

Compare to the original WPILib SwerveBot example to see how InputFactory
replaces manual deadband/inversion/slew rate code with config-driven
managed objects.

Run:
    cd examples/inputFactory
    python -m robotpy sim
"""

import logging
import os
import sys

# Add project root so we can import utils/
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", ".."))

import commands2  # noqa: E402
import wpilib  # noqa: E402
import wpilib.simulation  # noqa: E402

import drivetrain  # noqa: E402
from led import LEDSubsystem  # noqa: E402
from utils.input import InputFactory  # noqa: E402

log = logging.getLogger("ExampleRobot")


class MyRobot(commands2.TimedCommandRobot):
    """Example robot using InputFactory for all controller bindings."""

    def robotInit(self) -> None:
        # --- InputFactory ---
        # Create the factory first — this registers it as the active
        # instance so subsystems can call get_factory() to fetch
        # their own inputs without having them passed in.
        config_path = os.path.join(
            os.path.dirname(__file__), "controller_config.yaml")
        self.factory = InputFactory(config_path=config_path)

        # --- Drive axes ---
        # ManagedAnalog objects are callable — forward() returns the
        # fully shaped value (deadband, inversion, scale from YAML).
        # No manual applyDeadband() or axis inversion needed.
        forward = self.factory.getAnalog("drivetrain.forward")
        strafe = self.factory.getAnalog("drivetrain.strafe")
        rotate = self.factory.getAnalog("drivetrain.rotate")

        # --- Subsystems ---
        # Pass the ManagedAnalog callables directly to the drivetrain.
        # The drivetrain's default command reads them each cycle.
        self.swerve = drivetrain.Drivetrain(forward, strafe, rotate)

        # LED subsystem uses get_factory() internally to fetch its
        # own rumble control — no need to wire it up here.
        self.led = LEDSubsystem(channel=16)

        # --- Default command ---
        # The default command runs every cycle when no other command
        # requires the drivetrain.  It reads the axis callables stored
        # in the subsystem and calls drive().
        self.swerve.setDefaultCommand(
            self.swerve.defaultDriveCommand(fieldRelative=True))

        # --- Axis swap toggle ---
        # swap_axes is configured as toggle_on_true in the YAML.
        # .bind() reads that config and calls .toggleOnTrue() with
        # the drivetrain's swap command.  Each press swaps which
        # callable provides forward vs rotate inside the subsystem.
        self.factory.getButton("drivetrain.swap_axes").bind(
            self.swerve.swapAxesCommand())

        # --- LED bindings ---
        # .bind() auto-selects the trigger method from the YAML config:
        #   led.while_held has trigger_mode: while_true -> .whileTrue()
        #   led.toggle has trigger_mode: on_true -> .onTrue()
        self.factory.getButton("led.while_held").bind(
            self.led.whileHeldCommand())
        self.factory.getButton("led.toggle").bind(
            self.led.toggleCommand())

        # --- Sim rumble monitoring ---
        # In sim, rumble doesn't vibrate a physical controller.
        # Track the sim rumble value and log on change so we can
        # verify the rumble path is working.
        if wpilib.RobotBase.isSimulation():
            self._rumble_sim = wpilib.simulation.GenericHIDSim(0)
            self._last_rumble_left = 0.0
            self._last_rumble_right = 0.0

    def robotPeriodic(self) -> None:
        # Sync NT values into managed objects and handle rumble
        # timeouts.  Call this exactly once per cycle.
        self.factory.update()
        commands2.CommandScheduler.getInstance().run()

        # Log rumble changes in sim
        # Note that this is a work around since the sim does not seem
        # to let a attached controller rumble and does not display the rumble
        # in the joystick dialog
        if hasattr(self, "_rumble_sim"):
            RT = wpilib.XboxController.RumbleType
            left = self._rumble_sim.getRumble(RT.kLeftRumble)
            right = self._rumble_sim.getRumble(RT.kRightRumble)
            if left != self._last_rumble_left:
                log.info("Sim rumble left: %.2f -> %.2f",
                         self._last_rumble_left, left)
                self._last_rumble_left = left
            if right != self._last_rumble_right:
                log.info("Sim rumble right: %.2f -> %.2f",
                         self._last_rumble_right, right)
                self._last_rumble_right = right

    def autonomousPeriodic(self) -> None:
        self.swerve.updateOdometry()
