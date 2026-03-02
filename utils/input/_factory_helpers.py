"""Internal helpers for InputFactory.

Contains controller state, ntproperty dynamic class creation,
NT sync logic, and HID accessor builders.  Separated from factory.py
to keep the public InputFactory class front-and-center.

Why dynamic classes?
--------------------
We want every action (like "intake.run" or "drivetrain.speed") to have
its own NetworkTables entries so drivers can tune deadband, scale, etc.
from the dashboard.  The robotpy library provides ``ntproperty`` for
this, but it works as a **class-level descriptor** — meaning every
instance of the same class shares the same NT path.

Example of the problem::

    class ManagedAnalog:
        nt_deadband = ntproperty('/actions/deadband', 0.0)

    a = ManagedAnalog(...)  # reads /actions/deadband
    b = ManagedAnalog(...)  # ALSO reads /actions/deadband  <-- conflict!

Both ``a`` and ``b`` point to the same NT entry because ``nt_deadband``
is defined on the class, not the instance.

The solution is to create a **unique subclass for each action** at
runtime using Python's built-in ``type()`` function.  ``type()`` can
create new classes on the fly::

    # type(class_name, (parent_classes,), {attributes})
    MyClass = type('MyClass', (ManagedAnalog,), {
        'nt_deadband': ntproperty('/actions/intake/run/deadband', 0.05),
    })

Now ``MyClass`` is a brand-new class that inherits everything from
``ManagedAnalog`` but has its own ``nt_deadband`` pointing to a unique
NT path.  Each action gets its own subclass, so each gets its own
dashboard entries.

This pattern is called "dynamic class creation" or "metaprogramming."
It's the same thing that happens behind the scenes when you write a
normal ``class Foo:`` statement — Python just calls ``type()`` for you.
"""

import logging
from typing import Callable

import wpilib

from utils.controller.model import (
    ActionDefinition,
    ControllerConfig,
    InputType,
)
from utils.input.managed_analog import ManagedAnalog
from utils.input.managed_button import ManagedButton
from utils.input.managed_rumble import ManagedRumble
from utils.input.xbox_map import (
    AXIS_ACCESSORS,
    BUTTON_ACCESSORS,
    OUTPUT_ACCESSORS,
    POV_ANGLE_MAP,
    get_input_category,
)

log = logging.getLogger("InputFactory")


# ---------------------------------------------------------------------------
# Controller state
# ---------------------------------------------------------------------------

class ControllerState:
    """Internal state for a single controller port."""

    def __init__(self, port: int, config: ControllerConfig):
        self.port = port
        self.config = config
        self.controller = wpilib.XboxController(port)
        # Reverse map: action_qualified_name -> input_name
        self.action_to_input: dict[str, str] = {}
        for input_name, action_list in config.bindings.items():
            for action_name in action_list:
                self.action_to_input[action_name] = input_name


# ---------------------------------------------------------------------------
# ntproperty dynamic class creation
# ---------------------------------------------------------------------------

def make_analog_nt_class(nt_path: str, action: ActionDefinition) -> type:
    """Create a ManagedAnalog subclass with NT entries for this action.

    Uses ``type()`` to build a one-off class at runtime (see module
    docstring for why).  The returned class inherits all ManagedAnalog
    behavior but adds ``nt_deadband``, ``nt_scale``, etc. attributes
    that each point to a unique NT path like::

        /inputs/actions/intake/run/deadband
        /inputs/actions/intake/run/scale

    The factory creates one instance of this class per action.  The
    dashboard can then edit these NT values, and ``sync_analog_nt()``
    copies them into the managed object's local properties once per
    cycle so the shaping pipeline sees the updated values.
    """
    try:
        from ntcore.util import ntproperty
    except ImportError:
        return ManagedAnalog

    attrs = {
        'nt_deadband': ntproperty(
            f'{nt_path}/deadband', action.deadband, writeDefault=True),
        'nt_inversion': ntproperty(
            f'{nt_path}/inversion', action.inversion, writeDefault=True),
        'nt_scale': ntproperty(
            f'{nt_path}/scale', action.scale, writeDefault=True),
        'nt_slew_rate': ntproperty(
            f'{nt_path}/slew_rate', action.slew_rate, writeDefault=True),
        'nt_is_bound': ntproperty(
            f'{nt_path}/isBound', True, writeDefault=True),
        'nt_trigger_mode': ntproperty(
            f'{nt_path}/trigger_mode', action.trigger_mode.value,
            writeDefault=True),
        'nt_input_type': ntproperty(
            f'{nt_path}/input_type', action.input_type.value,
            writeDefault=True),
    }
    return type('ManagedAnalog_' + action.qualified_name.replace('.', '_'),
                (ManagedAnalog,), attrs)


def make_button_nt_class(nt_path: str, action: ActionDefinition) -> type:
    """Create a ManagedButton subclass with NT entries for this action.

    Same dynamic class pattern as ``make_analog_nt_class`` (see module
    docstring).  Buttons have fewer tunable params — mainly read-only
    info (trigger_mode, input_type, isBound).  BOOLEAN_TRIGGER actions
    also get a ``nt_threshold`` entry so the trigger threshold can be
    tuned from the dashboard.
    """
    try:
        from ntcore.util import ntproperty
    except ImportError:
        return ManagedButton

    attrs = {
        'nt_is_bound': ntproperty(
            f'{nt_path}/isBound', True, writeDefault=True),
        'nt_trigger_mode': ntproperty(
            f'{nt_path}/trigger_mode', action.trigger_mode.value,
            writeDefault=True),
        'nt_input_type': ntproperty(
            f'{nt_path}/input_type', action.input_type.value,
            writeDefault=True),
    }
    if action.input_type == InputType.BOOLEAN_TRIGGER:
        attrs['nt_threshold'] = ntproperty(
            f'{nt_path}/threshold', action.threshold, writeDefault=True)
    return type('ManagedButton_' + action.qualified_name.replace('.', '_'),
                (ManagedButton,), attrs)


def make_rumble_nt_class(nt_path: str, action: ActionDefinition) -> type:
    """Create a ManagedRumble subclass with NT entries for this action.

    Same dynamic class pattern as ``make_analog_nt_class`` (see module
    docstring).  Rumble outputs only publish read-only info (isBound,
    input_type) — no tunable params yet.
    """
    try:
        from ntcore.util import ntproperty
    except ImportError:
        return ManagedRumble

    attrs = {
        'nt_is_bound': ntproperty(
            f'{nt_path}/isBound', True, writeDefault=True),
        'nt_input_type': ntproperty(
            f'{nt_path}/input_type', action.input_type.value,
            writeDefault=True),
    }
    return type('ManagedRumble_' + action.qualified_name.replace('.', '_'),
                (ManagedRumble,), attrs)


# ---------------------------------------------------------------------------
# NT sync helpers
# ---------------------------------------------------------------------------

def sync_analog_nt(analog: ManagedAnalog) -> None:
    """Sync NT values into a ManagedAnalog's local properties.

    Skips parameters that have active custom NT mappings — those are
    handled separately by the managed object's ``_sync_custom_maps()``
    method, which reads from the user-specified NT path instead.
    """
    if not hasattr(analog, 'nt_deadband'):
        return

    mapped = analog.mapped_params

    if 'deadband' not in mapped:
        nt_db = analog.nt_deadband
        if nt_db != analog.deadband:
            analog.deadband = nt_db

    if 'inversion' not in mapped:
        nt_inv = analog.nt_inversion
        if nt_inv != analog.inversion:
            analog.inversion = nt_inv

    if 'scale' not in mapped:
        nt_sc = analog.nt_scale
        if nt_sc != analog.scale:
            analog.scale = nt_sc

    if 'slew_rate' not in mapped:
        nt_sr = analog.nt_slew_rate
        if nt_sr != analog.slew_rate:
            analog.slew_rate = nt_sr


def sync_button_nt(btn: ManagedButton) -> None:
    """Sync NT values into a ManagedButton (threshold for BOOLEAN_TRIGGER).

    Skips parameters that have active custom NT mappings.
    """
    if not hasattr(btn, 'nt_threshold'):
        return

    mapped = btn.mapped_params
    if 'threshold' in mapped:
        return

    # BOOLEAN_TRIGGER threshold changes require rebuilding the
    # condition — this is a future enhancement. For now we just
    # read and log.


# ---------------------------------------------------------------------------
# HID accessor builders
# ---------------------------------------------------------------------------

def _is_connected(port: int) -> bool:
    """Check if a joystick is connected (avoids per-cycle warning spam)."""
    return wpilib.DriverStation.isJoystickConnected(port)


def make_button_condition(
    state: ControllerState,
    input_name: str,
    action: ActionDefinition,
) -> Callable[[], bool]:
    """Build a boolean condition for a button/POV/BOOLEAN_TRIGGER.

    Returns False when the controller is disconnected to avoid
    per-cycle warning spam from wpilib in simulation.
    """
    category = get_input_category(input_name)
    ctrl = state.controller
    port = state.port

    if category == "button":
        accessor = BUTTON_ACCESSORS[input_name]
        return lambda: accessor(ctrl) if _is_connected(port) else False

    elif category == "pov":
        target_angle = POV_ANGLE_MAP[input_name]
        return lambda: (
            ctrl.getPOV() == target_angle
            if _is_connected(port) else False)

    elif category == "axis":
        # BOOLEAN_TRIGGER — axis > threshold = True
        axis_fn = AXIS_ACCESSORS[input_name]
        threshold = action.threshold
        return lambda: (
            axis_fn(ctrl) > threshold
            if _is_connected(port) else False)

    else:
        log.error(
            "Cannot make button condition for '%s' "
            "(category: %s)", input_name, category)
        return lambda: False


def make_axis_accessor(
    state: ControllerState,
    input_name: str,
) -> Callable[[], float]:
    """Build a raw axis accessor.

    Returns 0.0 when the controller is disconnected to avoid
    per-cycle warning spam from wpilib in simulation.
    """
    category = get_input_category(input_name)
    ctrl = state.controller
    port = state.port

    if category == "axis":
        accessor = AXIS_ACCESSORS[input_name]
        return lambda: accessor(ctrl) if _is_connected(port) else 0.0

    # Allow buttons to be read as 0.0/1.0 for edge cases
    elif category == "button":
        accessor = BUTTON_ACCESSORS[input_name]
        return lambda: (
            (1.0 if accessor(ctrl) else 0.0)
            if _is_connected(port) else 0.0)

    elif category == "pov":
        target_angle = POV_ANGLE_MAP[input_name]
        return lambda: (
            (1.0 if ctrl.getPOV() == target_angle else 0.0)
            if _is_connected(port) else 0.0)

    else:
        log.error(
            "Cannot make axis accessor for '%s' "
            "(category: %s)", input_name, category)
        return lambda: 0.0


def make_output_setter(
    state: ControllerState,
    input_name: str,
) -> Callable[[float], None]:
    """Build a rumble output setter.

    No-ops when the controller is disconnected.
    """
    if input_name in OUTPUT_ACCESSORS:
        setter = OUTPUT_ACCESSORS[input_name]
        ctrl = state.controller
        port = state.port
        def _set_rumble(v):
            if _is_connected(port):
                log.debug("Rumble '%s' port=%d -> %.2f", input_name, port, v)
                setter(ctrl, v)
        return _set_rumble

    log.error("'%s' is not a rumble output", input_name)
    return lambda v: None


def publish_bindings_nt(
    nt_base: str,
    controllers: "dict[int, ControllerState]",
) -> None:
    """Publish the binding map to NT (read-only informational)."""
    try:
        from ntcore.util import ntproperty  # noqa: F401
        import ntcore
        inst = ntcore.NetworkTableInstance.getDefault()
        table = inst.getTable(f"{nt_base}/bindings")

        for state in controllers.values():
            ctrl_name = state.config.name or f"port{state.port}"
            for input_name, actions in state.config.bindings.items():
                for action_name in actions:
                    table.getSubTable(ctrl_name).getSubTable(
                        input_name).putString("action", action_name)
    except ImportError:
        pass
