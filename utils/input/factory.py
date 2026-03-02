"""InputFactory — config-driven controller input management.

Loads a FullConfig (from YAML or pre-built), creates wpilib
XboxControllers, and provides factory methods that return managed
input objects (ManagedButton, ManagedAnalog, ManagedRumble).

All action parameters are published to NetworkTables via ntproperty
for runtime dashboard tuning.  NT sync is handled automatically each
scheduler cycle via an internal subsystem.

Usage::

    factory = InputFactory(config_path="data/inputs/controller.yaml")
    speed = factory.getAnalog("drivetrain.speed")
    fire = factory.getButton("intake.run")
    rumble = factory.getRumbleControl("general.rumble_left")
"""

import logging
from pathlib import Path
from typing import Callable

import commands2
import wpilib

from utils.controller.model import (
    FullConfig,
    InputType,
    EventTriggerMode,
)
from utils.controller.config_io import (
    load_config,
    load_actions_from_file,
    load_assignments_from_file,
)
from utils.input.managed_button import ManagedButton
from utils.input.managed_analog import ManagedAnalog
from utils.input.managed_rumble import ManagedRumble
from utils.input.shaping import build_shaping_pipeline
from utils.input._factory_helpers import (
    ControllerState,
    make_analog_nt_class,
    make_axis_accessor,
    make_button_condition,
    make_button_nt_class,
    make_output_setter,
    make_rumble_nt_class,
    publish_bindings_nt,
    sync_analog_nt,
    sync_button_nt,
)

log = logging.getLogger("InputFactory")

# NT base path for all input-related entries
_NT_BASE = "/inputs"

# Module-level singleton — set by InputFactory.__init__
_active_factory: "InputFactory | None" = None


def get_factory() -> "InputFactory":
    """Return the active InputFactory instance.

    Allows any module (subsystems, commands, etc.) to fetch managed
    inputs without having the factory passed through constructors::

        from utils.input import get_factory
        rumble = get_factory().getRumbleControl("feedback.rumble")

    Raises RuntimeError if no factory has been created yet.
    """
    if _active_factory is None:
        raise RuntimeError(
            "InputFactory not initialized — create one in robotInit "
            "before calling get_factory()")
    return _active_factory


class _FactoryUpdater(commands2.Subsystem):
    """Internal subsystem that runs factory NT sync each scheduler cycle.

    Registered with the CommandScheduler on construction.  The scheduler
    iterates subsystem ``periodic()`` calls in registration order (dict
    insertion order).  Because the factory is created in ``robotInit``
    before any user subsystems, this updater is the first registered
    subsystem and its ``periodic()`` runs before all others — ensuring
    managed inputs have fresh NT values before any subsystem reads them.
    """

    def __init__(self, factory: "InputFactory"):
        super().__init__()
        self._factory = factory

    def periodic(self) -> None:
        self._factory._update()


class InputFactory:
    """Config-driven controller input factory.

    Loads configuration and creates managed input objects that wrap
    wpilib HID devices with config-driven shaping, validation, and
    NetworkTables publishing.

    Args:
        config: Pre-built FullConfig object (for testing).
        config_path: Path to a single YAML with actions + controllers.
        actions_path: Path to actions-only YAML (used with assignments_path).
        assignments_path: Path to controllers-only YAML.
        register_global: Controls singleton registration for get_factory().
            None (default) — register only if no factory exists yet
            (first-created wins).  True — always register, replacing any
            existing factory.  False — never register (standalone instance,
            invisible to get_factory()).

    Precedence: config > config_path > (actions_path + assignments_path)
    """

    def __init__(
        self,
        config: FullConfig | None = None,
        config_path: str | Path | None = None,
        actions_path: str | Path | None = None,
        assignments_path: str | Path | None = None,
        register_global: bool | None = None,
    ):
        # Load configuration and track source for error messages
        if config is not None:
            self._config = config
            self._config_source = "<FullConfig object>"
        elif config_path is not None:
            self._config = load_config(config_path)
            self._config_source = str(config_path)
        elif actions_path is not None and assignments_path is not None:
            actions = load_actions_from_file(actions_path)
            controllers = load_assignments_from_file(assignments_path)
            self._config = FullConfig(
                actions=actions, controllers=controllers)
            self._config_source = (
                f"{actions_path} + {assignments_path}")
        else:
            raise ValueError(
                "Must provide config, config_path, or "
                "(actions_path + assignments_path)")

        # Create controller instances
        self._controllers: dict[int, ControllerState] = {}
        for port, ctrl_config in self._config.controllers.items():
            self._controllers[port] = ControllerState(port, ctrl_config)

        # Publish raw controllers to NT for dashboard inspection.
        # Only publish if connected — avoids warning spam in sim
        # when no joystick is plugged in (Sendable queries axes).
        for port, state in self._controllers.items():
            if wpilib.DriverStation.isJoystickConnected(port):
                wpilib.SmartDashboard.putData(
                    f"{_NT_BASE}/controllers/raw/{port}",
                    state.controller)

        # Publish bindings info to NT
        publish_bindings_nt(_NT_BASE, self._controllers)

        # Caches — all factory methods return the same object for a name
        self._buttons: dict[str, ManagedButton] = {}
        self._analogs: dict[str, ManagedAnalog] = {}
        self._rumbles: dict[str, ManagedRumble] = {}

        # Register as the active factory for get_factory().
        # register_global=None (default): register only if no factory exists yet.
        # register_global=True: always register (override existing).
        # register_global=False: never register (standalone factory).
        global _active_factory
        if register_global is True:
            _active_factory = self
        elif register_global is None and _active_factory is None:
            _active_factory = self

        # Register an internal subsystem that syncs NT values each cycle.
        # The CommandScheduler iterates subsystems in registration order
        # (dict insertion order in Python 3.7+).  Since the factory is
        # created in robotInit before user subsystems, this updater is
        # registered first and its periodic() runs before all others.
        scheduler = commands2.CommandScheduler.getInstance()
        if scheduler._subsystems:
            log.warning(
                "InputFactory created after %d other subsystem(s) — "
                "NT sync may run after those subsystems read stale "
                "values for one cycle. Create the factory before any "
                "subsystems to guarantee ordering.",
                len(scheduler._subsystems))
        self._updater = _FactoryUpdater(self)

    @property
    def config(self) -> FullConfig:
        """The loaded configuration."""
        return self._config

    # --- Name resolution ---

    def _resolve_name(self, name: str, group: str | None) -> str:
        """Resolve a name to a fully qualified action name.

        - "group.name" -> "group.name" (dot present, group param ignored)
        - ("name", group="intake") -> "intake.name"
        - ("name", group=None) -> "general.name"
        """
        if '.' in name:
            return name
        g = group if group is not None else "general"
        return f"{g}.{name}"

    def _find_binding(self, qualified_name: str
                      ) -> tuple[ControllerState, str] | None:
        """Find which controller+input is bound to the given action.

        Returns (controller_state, input_name) or None if not bound.
        """
        for state in self._controllers.values():
            if qualified_name in state.action_to_input:
                return state, state.action_to_input[qualified_name]
        return None

    # --- Factory methods ---

    def getButton(
        self,
        name: str,
        group: str | None = None,
        required: bool = True,
        default_value: bool = False,
    ) -> ManagedButton:
        """Get a managed button for the named action.

        Handles InputType.BUTTON, POV, and BOOLEAN_TRIGGER.

        Args:
            name: Action name — either qualified "group.name" or short
                "name".  If no dot is present and group is None, the
                "general" group is assumed (e.g. "fire" -> "general.fire").
            group: Explicit group override (used when name has no dot).
            required: If True, raise KeyError when not found/not bound.
            default_value: Value returned if unbound.

        Returns:
            ManagedButton wrapping a Trigger with the configured binding.
        """
        qn = self._resolve_name(name, group)

        # Return cached if exists
        if qn in self._buttons:
            return self._buttons[qn]

        action = self._config.actions.get(qn)
        binding = self._find_binding(qn)

        if action is None:
            if required:
                raise KeyError(
                    f"Action '{qn}' not found in config "
                    f"({self._config_source})")
            log.warning("Action '%s' not found, returning default", qn)
            btn = ManagedButton(None, lambda: default_value, default_value)
            self._buttons[qn] = btn
            return btn

        if binding is None:
            if required:
                raise KeyError(
                    f"Action '{qn}' exists but is not bound to any "
                    f"input ({self._config_source})")
            log.warning("Action '%s' not bound, returning default", qn)
            btn = ManagedButton(
                action, lambda: default_value, default_value)
            self._buttons[qn] = btn
            return btn

        state, input_name = binding
        condition = make_button_condition(state, input_name, action)

        # Create NT-enabled subclass
        nt_path = f"{_NT_BASE}/actions/{action.group}/{action.name}"
        klass = make_button_nt_class(nt_path, action)
        btn = klass(action, condition, default_value)
        self._buttons[qn] = btn
        return btn

    def getRawButton(
        self,
        name: str,
        group: str | None = None,
        required: bool = True,
    ) -> Callable[[], bool]:
        """Get a plain callable returning the button state.

        No Trigger wrapping, no command binding — just a function.
        For BOOLEAN_TRIGGER: returns lambda applying threshold comparison.

        Args:
            name: Action name — either qualified "group.name" or short
                "name".  If no dot is present and group is None, the
                "general" group is assumed (e.g. "fire" -> "general.fire").
            group: Explicit group override (used when name has no dot).
            required: If True, raise KeyError when not found/not bound.
        """
        qn = self._resolve_name(name, group)
        action = self._config.actions.get(qn)
        binding = self._find_binding(qn)

        if action is None or binding is None:
            if required:
                raise KeyError(
                    f"Action '{qn}' not found or not bound "
                    f"({self._config_source})")
            log.warning("Action '%s' unavailable, returning False", qn)
            return lambda: False

        state, input_name = binding
        return make_button_condition(state, input_name, action)

    def getAnalog(
        self,
        name: str,
        group: str | None = None,
        required: bool = True,
        default_value: float = 0.0,
    ) -> ManagedAnalog:
        """Get a managed analog input for the named action.

        Handles InputType.ANALOG.  Full shaping pipeline from config.

        Args:
            name: Action name — either qualified "group.name" or short
                "name".  If no dot is present and group is None, the
                "general" group is assumed (e.g. "speed" -> "general.speed").
            group: Explicit group override (used when name has no dot).
            required: If True, raise KeyError when not found/not bound.
            default_value: Value returned if unbound.

        Returns:
            ManagedAnalog — callable returning shaped value.
        """
        qn = self._resolve_name(name, group)

        if qn in self._analogs:
            return self._analogs[qn]

        action = self._config.actions.get(qn)
        binding = self._find_binding(qn)

        if action is None:
            if required:
                raise KeyError(
                    f"Action '{qn}' not found in config "
                    f"({self._config_source})")
            log.warning("Action '%s' not found, returning default", qn)
            analog = ManagedAnalog(
                None, lambda: default_value, default_value)
            self._analogs[qn] = analog
            return analog

        if action.input_type == InputType.VIRTUAL_ANALOG:
            raise NotImplementedError(
                f"VIRTUAL_ANALOG is reserved for future use "
                f"(action '{qn}') ({self._config_source})")

        if binding is None:
            if required:
                raise KeyError(
                    f"Action '{qn}' exists but is not bound to any "
                    f"input ({self._config_source})")
            log.warning("Action '%s' not bound, returning default", qn)
            analog = ManagedAnalog(
                action, lambda: default_value, default_value)
            self._analogs[qn] = analog
            return analog

        state, input_name = binding
        accessor = make_axis_accessor(state, input_name)

        # Create NT-enabled subclass
        nt_path = f"{_NT_BASE}/actions/{action.group}/{action.name}"
        klass = make_analog_nt_class(nt_path, action)
        analog = klass(action, accessor, default_value)
        self._analogs[qn] = analog
        return analog

    def getAnalogRaw(
        self,
        name: str,
        group: str | None = None,
        required: bool = True,
        apply_invert: bool = False,
        apply_deadband: bool = False,
        apply_scale: bool = False,
    ) -> Callable[[], float]:
        """Get a callable returning a selectively-shaped axis value.

        Only applies the requested transformations.  Does not create
        a managed object — returns a plain callable.

        Args:
            name: Action name — either qualified "group.name" or short
                "name".  If no dot is present and group is None, the
                "general" group is assumed.
            group: Explicit group override (used when name has no dot).
            required: If True, raise KeyError when unavailable.
            apply_invert: Apply inversion from config.
            apply_deadband: Apply deadband from config.
            apply_scale: Apply scale from config.
        """
        qn = self._resolve_name(name, group)
        action = self._config.actions.get(qn)
        binding = self._find_binding(qn)

        if action is None or binding is None:
            if required:
                raise KeyError(
                    f"Action '{qn}' not found or not bound "
                    f"({self._config_source})")
            log.warning("Action '%s' unavailable, returning 0.0", qn)
            return lambda: 0.0

        state, input_name = binding
        raw_accessor = make_axis_accessor(state, input_name)

        # Build a selective pipeline
        pipeline = build_shaping_pipeline(
            inversion=action.inversion if apply_invert else False,
            deadband=action.deadband if apply_deadband else 0.0,
            trigger_mode=EventTriggerMode.RAW,
            scale=action.scale if apply_scale else 1.0,
            extra={},
        )

        def _selective():
            return pipeline(raw_accessor())
        return _selective

    def getRumbleControl(
        self,
        name: str,
        group: str | None = None,
        required: bool = True,
    ) -> ManagedRumble:
        """Get a managed rumble output for the named action.

        Args:
            name: Action name — either qualified "group.name" or short
                "name".  If no dot is present and group is None, the
                "general" group is assumed.
            group: Explicit group override (used when name has no dot).
            required: If True, raise KeyError when unavailable.

        Returns:
            ManagedRumble with set(value, timeout) interface.
        """
        qn = self._resolve_name(name, group)

        if qn in self._rumbles:
            return self._rumbles[qn]

        action = self._config.actions.get(qn)
        binding = self._find_binding(qn)

        if action is None:
            if required:
                raise KeyError(
                    f"Action '{qn}' not found in config "
                    f"({self._config_source})")
            log.warning("Action '%s' not found, returning no-op rumble", qn)
            rumble = ManagedRumble(None, lambda v: None)
            self._rumbles[qn] = rumble
            return rumble

        if binding is None:
            if required:
                raise KeyError(
                    f"Action '{qn}' exists but is not bound to any "
                    f"input ({self._config_source})")
            log.warning("Action '%s' not bound, returning no-op rumble", qn)
            rumble = ManagedRumble(action, lambda v: None)
            self._rumbles[qn] = rumble
            return rumble

        state, input_name = binding
        setter = make_output_setter(state, input_name)

        # Create NT-enabled subclass
        nt_path = f"{_NT_BASE}/actions/{action.group}/{action.name}"
        klass = make_rumble_nt_class(nt_path, action)
        rumble = klass(action, setter)
        self._rumbles[qn] = rumble
        return rumble

    # --- Controller access ---

    def getController(self, port: int) -> wpilib.XboxController | None:
        """Get the raw XboxController for a given port (for telemetry/logging)."""
        state = self._controllers.get(port)
        return state.controller if state is not None else None

    # --- Periodic sync (called automatically by _FactoryUpdater) ---

    def _update(self) -> None:
        """Sync NT values into managed objects and handle rumble timeouts.

        Called automatically each scheduler cycle by ``_FactoryUpdater``.
        Because the factory registers before user subsystems, this runs
        first — so managed inputs have fresh NT values before any
        subsystem reads them.

        NT values are read once per cycle and compared against cached
        local values.  If a dashboard change is detected, the local
        property is updated and the pipeline is rebuilt.  This prevents
        mid-cycle inconsistency — all reads within a single cycle see
        the same parameter snapshot.

        Custom NT mappings (from ``mapParamToNtPath()``) are synced
        after the auto-generated NT sync.  Parameters with custom
        mappings are skipped during auto-generated sync to prevent
        conflicts.

        All NT reads (both auto-generated and custom) happen here in
        the main robot loop — not via ntcore listeners — because
        listener callbacks fire on a background thread and would race
        with property reads during pipeline execution.
        """
        # Sync NT -> ManagedAnalog properties
        for analog in self._analogs.values():
            if analog.action is None:
                continue
            sync_analog_nt(analog)
            analog._sync_custom_maps()

        # Sync NT -> ManagedButton properties (BOOLEAN_TRIGGER threshold)
        for btn in self._buttons.values():
            if btn.action is None:
                continue
            sync_button_nt(btn)
            btn._sync_custom_maps()

        # Update rumble timeouts
        for rumble in self._rumbles.values():
            rumble.update()

    # --- Future: dynamic remapping ---

    def remap(self, action_name: str, port: int,
              input_name: str) -> None:
        """Swap the physical input for a named action.

        Not implemented — reserved for future dynamic remapping.
        """
        raise NotImplementedError("Dynamic remapping not yet implemented")
