"""ManagedRumble — output setter with optional timeout.

Wraps a rumble output channel with set/stop/timeout functionality.
The factory calls update() each cycle to handle timeouts.
"""

import time
from typing import Callable

from utils.controller.model import ActionDefinition


class ManagedRumble:
    """A managed rumble output channel.

    Args:
        action: The ActionDefinition this output represents (may be None).
        setter: Callable that sets the rumble intensity (0.0 to 1.0).
    """

    def __init__(
        self,
        action: ActionDefinition | None,
        setter: Callable[[float], None],
    ):
        self._action = action
        self._setter = setter
        self._stop_time: float | None = None
        self._current_value: float = 0.0

    @property
    def action(self) -> ActionDefinition | None:
        return self._action

    def set(self, value: float, timeout: float = 0.0) -> None:
        """Set rumble intensity.

        Args:
            value: Intensity from 0.0 to 1.0.
            timeout: If > 0, auto-stop after this many seconds.
        """
        self._current_value = value
        self._setter(value)
        if timeout > 0:
            self._stop_time = time.monotonic() + timeout
        else:
            self._stop_time = None

    def stop(self) -> None:
        """Stop the rumble immediately."""
        self._current_value = 0.0
        self._setter(0.0)
        self._stop_time = None

    def update(self) -> None:
        """Check timeouts — call once per robot cycle."""
        if (self._stop_time is not None
                and time.monotonic() >= self._stop_time):
            self.stop()

    def _rebind(self, setter: Callable[[float], None]) -> None:
        """Swap the output setter for dynamic remapping."""
        self._setter = setter
