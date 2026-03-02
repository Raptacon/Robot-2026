"""ManagedButton — wraps a commands2 Trigger with action metadata.

Provides the same binding API as Trigger (.onTrue, .whileTrue, etc.)
but adds config-driven auto-binding via .bind() and supports future
dynamic remapping through _rebind().
"""

from typing import Callable

import commands2
from commands2.button import Trigger

from utils.controller.model import ActionDefinition, EventTriggerMode


class ManagedButton:
    """A managed boolean input backed by a Trigger.

    Args:
        action: The ActionDefinition this button represents (may be None
                for unbound/default buttons).
        condition: Callable returning the current boolean state.
        default_value: Value returned when no condition is bound.
    """

    def __init__(
        self,
        action: ActionDefinition | None,
        condition: Callable[[], bool],
        default_value: bool = False,
    ):
        self._action = action
        self._condition = condition
        self._default_value = default_value
        self._trigger = Trigger(condition)

    # --- Drop-in Trigger binding methods ---

    def onTrue(self, command: commands2.Command) -> "ManagedButton":
        """Schedule command when condition becomes True."""
        self._trigger.onTrue(command)
        return self

    def onFalse(self, command: commands2.Command) -> "ManagedButton":
        """Schedule command when condition becomes False."""
        self._trigger.onFalse(command)
        return self

    def whileTrue(self, command: commands2.Command) -> "ManagedButton":
        """Schedule command while condition is True, cancel on False."""
        self._trigger.whileTrue(command)
        return self

    def whileFalse(self, command: commands2.Command) -> "ManagedButton":
        """Schedule command while condition is False, cancel on True."""
        self._trigger.whileFalse(command)
        return self

    def toggleOnTrue(self, command: commands2.Command) -> "ManagedButton":
        """Toggle command scheduling each time condition becomes True."""
        self._trigger.toggleOnTrue(command)
        return self

    _BINDING_MAP = {
        EventTriggerMode.ON_TRUE: "onTrue",
        EventTriggerMode.ON_FALSE: "onFalse",
        EventTriggerMode.WHILE_TRUE: "whileTrue",
        EventTriggerMode.WHILE_FALSE: "whileFalse",
        EventTriggerMode.TOGGLE_ON_TRUE: "toggleOnTrue",
    }

    def bind(
        self,
        command: commands2.Command,
        mode: EventTriggerMode | None = None,
    ) -> "ManagedButton":
        """Bind a command using the configured or overridden trigger mode.

        Args:
            command: The command to bind.
            mode: Override the YAML-configured trigger mode.  When None
                (default), uses the action's configured mode.  Pass an
                explicit EventTriggerMode to ignore the config, e.g.
                ``btn.bind(cmd, mode=EventTriggerMode.WHILE_TRUE)``.

        Falls back to onTrue when no action is set and no override given.
        """
        if mode is None:
            mode = (self._action.trigger_mode
                    if self._action is not None
                    else EventTriggerMode.ON_TRUE)
        method_name = self._BINDING_MAP.get(mode, "onTrue")
        return getattr(self, method_name)(command)

    # --- State access ---

    def get(self) -> bool:
        """Return the current boolean state."""
        return self._condition()

    @property
    def trigger(self) -> Trigger:
        """Access the underlying Trigger for advanced composition."""
        return self._trigger

    @property
    def action(self) -> ActionDefinition | None:
        """The action definition, if any."""
        return self._action

    # --- Remapping support ---

    def _rebind(self, condition: Callable[[], bool]) -> None:
        """Swap the condition and rebuild the internal Trigger.

        Used by factory.remap() for dynamic remapping.
        Note: existing command bindings on the old Trigger will no
        longer fire — callers must re-register bindings after remap.
        """
        self._condition = condition
        self._trigger = Trigger(condition)
