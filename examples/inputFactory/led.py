"""Simple LED subsystem — outputs on a DIO channel.

Demonstrates a minimal subsystem that:
  - Uses utils.input.get_factory() to fetch its own rumble control directly
  - Provides command factories for button bindings
  - Drives rumble feedback based on LED state in periodic()
"""

import logging

import commands2
import wpilib
import utils.input

log = logging.getLogger("LEDSubsystem")


class LEDSubsystem(commands2.SubsystemBase):
    """Controls a single LED connected to a digital output.

    Fetches a rumble control from the active InputFactory to provide
    haptic feedback when the LED is on.  No need to pass the factory
    or rumble object through the constructor — utils.input.get_factory() provides
    global access after the factory is created in robotInit.
    """

    def __init__(
        self,
        channel: int = 0,
        rumble_action: str = "feedback.rumble",
        rumble_intensity: float = 0.3,
    ) -> None:
        super().__init__()
        self._output = wpilib.DigitalOutput(channel)
        self._on = False
        self._rumble_intensity = rumble_intensity

        # Fetch rumble directly from the active factory.
        # required=False so the subsystem still works if
        # the rumble action isn't configured.
        self._rumble = utils.input.get_factory().getRumbleControl(
            rumble_action, required=False)

    @property
    def isOn(self) -> bool:
        return self._on

    def setLED(self, on: bool) -> None:
        self._on = on
        self._output.set(on)

    def toggle(self) -> None:
        self.setLED(not self._on)

    def periodic(self) -> None:
        """Called every cycle by the command scheduler.

        Drives rumble output to match LED state — gentle rumble
        while the LED is on, off when the LED is off.
        """
        self._rumble.set(
            self._rumble_intensity if self._on else 0.0)

    # --- Command factories ---

    def onCommand(self) -> commands2.Command:
        """Return a command that turns the LED on (runs once)."""
        return commands2.InstantCommand(
            lambda: self.setLED(True), self
        ).withName("LED On")

    def offCommand(self) -> commands2.Command:
        """Return a command that turns the LED off (runs once)."""
        return commands2.InstantCommand(
            lambda: self.setLED(False), self
        ).withName("LED Off")

    def whileHeldCommand(self) -> commands2.Command:
        """Return a command that lights the LED while held.

        StartEnd: runs the first lambda on init, second on end.
        The LED turns on immediately and off when the command ends
        (button released).
        """
        return commands2.StartEndCommand(
            lambda: (self.setLED(True), log.info("LED on (held)")),
            lambda: (self.setLED(False), log.info("LED off (released)")),
            self,
        ).withName("LED While Held")

    def toggleCommand(self) -> commands2.Command:
        """Return a command that toggles the LED (runs once)."""
        def _toggle():
            self.toggle()
            log.info("LED toggled -> %s", "ON" if self._on else "OFF")
        return commands2.InstantCommand(
            _toggle, self
        ).withName("LED Toggle")
