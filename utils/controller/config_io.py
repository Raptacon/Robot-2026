"""YAML load/save for controller configuration.

Handles serialization of FullConfig to/from human-readable YAML.
Omits default values for cleaner output and preserves unknown fields
in the ``extra`` dict for forward compatibility.

Actions are stored in a nested format grouped by their ``group`` field::

    actions:
      general:
        fire_shooter:
          description: Fire the Shooter
      intake:
        run:
          description: Run intake

Backward compatibility: old flat-format files (no group nesting) are
loaded with all actions placed in the ``"general"`` group, and bare
binding names are upgraded to qualified names automatically.

No wpilib dependencies - pure Python + PyYAML.
"""

from pathlib import Path

import yaml

from .model import (
    ActionDefinition,
    BUTTON_TRIGGER_MODES,
    ControllerConfig,
    FullConfig,
    InputType,
    TriggerMode,
)

# Defaults used to decide which fields to omit from YAML output
_ACTION_DEFAULTS = ActionDefinition(name="")

# Known ActionDefinition fields used for format detection
_ACTION_FIELD_NAMES = {
    "description", "input_type", "trigger_mode",
    "deadband", "inversion", "scale", "extra",
}


def _action_to_dict(action: ActionDefinition) -> dict:
    """Serialize an ActionDefinition, omitting fields that match defaults."""
    d = {}
    if action.description:
        d["description"] = action.description
    if action.input_type != _ACTION_DEFAULTS.input_type:
        d["input_type"] = action.input_type.value
    if action.trigger_mode != _ACTION_DEFAULTS.trigger_mode:
        d["trigger_mode"] = action.trigger_mode.value
    if action.deadband != _ACTION_DEFAULTS.deadband:
        d["deadband"] = action.deadband
    if action.inversion != _ACTION_DEFAULTS.inversion:
        d["inversion"] = action.inversion
    if action.scale != _ACTION_DEFAULTS.scale:
        d["scale"] = action.scale
    if action.extra:
        d["extra"] = action.extra
    return d


# Backward compat: old configs may use "axis" instead of "analog"
_INPUT_TYPE_MIGRATION = {"axis": "analog"}


def _dict_to_action(name: str, d: dict, group: str = "general") -> ActionDefinition:
    """Deserialize an ActionDefinition from a YAML dict."""
    if d is None:
        d = {}
    raw_input_type = d.get("input_type", InputType.BUTTON.value)
    raw_input_type = _INPUT_TYPE_MIGRATION.get(raw_input_type, raw_input_type)
    input_type = InputType(raw_input_type)

    # Determine appropriate default trigger mode based on input type
    if input_type == InputType.ANALOG:
        default_trigger = TriggerMode.SCALED.value
    else:
        default_trigger = TriggerMode.ON_TRUE.value
    raw_trigger = d.get("trigger_mode", default_trigger)

    # Migrate button trigger modes on analog inputs to scaled
    trigger_mode = TriggerMode(raw_trigger)
    button_values = {m.value for m in BUTTON_TRIGGER_MODES}
    if input_type == InputType.ANALOG and trigger_mode.value in button_values:
        trigger_mode = TriggerMode.SCALED

    return ActionDefinition(
        name=name,
        description=d.get("description", ""),
        group=group,
        input_type=input_type,
        trigger_mode=trigger_mode,
        deadband=float(d.get("deadband", 0.0)),
        inversion=bool(d.get("inversion", False)),
        scale=float(d.get("scale", 1.0)),
        extra=d.get("extra", {}),
    )


def _controller_to_dict(ctrl: ControllerConfig) -> dict:
    """Serialize a ControllerConfig."""
    d = {}
    if ctrl.name:
        d["name"] = ctrl.name
    if ctrl.controller_type != "xbox":
        d["controller_type"] = ctrl.controller_type
    if ctrl.bindings:
        d["bindings"] = {
            input_name: list(actions)
            for input_name, actions in ctrl.bindings.items()
            if actions
        }
    return d


def _dict_to_controller(port: int, d: dict) -> ControllerConfig:
    """Deserialize a ControllerConfig from a YAML dict."""
    if d is None:
        d = {}
    bindings = {}
    raw_bindings = d.get("bindings", {})
    if raw_bindings:
        for input_name, actions in raw_bindings.items():
            if isinstance(actions, str):
                bindings[input_name] = [actions]
            elif isinstance(actions, list):
                bindings[input_name] = [str(a) for a in actions]
    return ControllerConfig(
        port=port,
        name=d.get("name", ""),
        controller_type=d.get("controller_type", "xbox"),
        bindings=bindings,
    )


# --- Format Detection ---

def _is_nested_format(actions_data: dict) -> bool:
    """Detect whether actions use nested (grouped) or flat (legacy) format.

    Nested format: ``actions -> group_name -> action_name -> {fields}``
    Flat format:   ``actions -> action_name -> {fields}``

    Heuristic: if any top-level value is a dict whose keys overlap with
    known ActionDefinition field names, it's flat format.  Otherwise
    (values are dicts-of-dicts or None), it's nested.
    """
    if not actions_data:
        return False
    for value in actions_data.values():
        if value is None:
            # ``action_name:`` with no fields -> flat
            return False
        if isinstance(value, dict):
            if value.keys() & _ACTION_FIELD_NAMES:
                return False
        else:
            # Primitive value -> flat
            return False
    return True


def _load_actions_dict(actions_data: dict) -> dict[str, ActionDefinition]:
    """Load actions from either nested or flat YAML format.

    Returns dict keyed by qualified name (``group.action_name``).
    """
    if not actions_data:
        return {}

    actions = {}
    if _is_nested_format(actions_data):
        for group_name, group_actions in actions_data.items():
            group_name = str(group_name)
            if not isinstance(group_actions, dict):
                continue
            for action_name, action_dict in group_actions.items():
                action = _dict_to_action(str(action_name), action_dict, group=group_name)
                actions[action.qualified_name] = action
    else:
        for action_name, action_dict in actions_data.items():
            action = _dict_to_action(str(action_name), action_dict, group="general")
            actions[action.qualified_name] = action

    return actions


def _actions_to_nested_dict(actions: dict[str, ActionDefinition]) -> dict:
    """Group actions by group and serialize to nested dict."""
    groups: dict[str, dict[str, dict]] = {}
    for action in actions.values():
        group = action.group
        if group not in groups:
            groups[group] = {}
        groups[group][action.name] = _action_to_dict(action)
    return groups


def _migrate_bindings(controllers: dict[int, ControllerConfig],
                      actions: dict[str, ActionDefinition]) -> None:
    """Upgrade bare action names in bindings to qualified names.

    If a binding value ``foo`` is not in *actions* but ``general.foo`` is,
    replace it.  Handles backward compatibility with old flat configs.
    """
    action_keys = set(actions.keys())
    for ctrl in controllers.values():
        for input_name, action_list in ctrl.bindings.items():
            ctrl.bindings[input_name] = [
                f"general.{a}"
                if a not in action_keys and f"general.{a}" in action_keys
                else a
                for a in action_list
            ]


# --- Public API ---

def save_config(config: FullConfig, path: str | Path) -> None:
    """Save a FullConfig to a YAML file (nested action format)."""
    data = {}

    if config.actions:
        data["actions"] = _actions_to_nested_dict(config.actions)

    if config.controllers:
        data["controllers"] = {
            port: _controller_to_dict(ctrl)
            for port, ctrl in config.controllers.items()
        }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_config(path: str | Path) -> FullConfig:
    """Load a FullConfig from a YAML file.

    Supports both nested (grouped) and flat (legacy) action formats.
    """
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)

    if not data:
        return FullConfig()

    actions = _load_actions_dict(data.get("actions") or {})

    controllers = {}
    for port, ctrl_dict in (data.get("controllers") or {}).items():
        port = int(port)
        controllers[port] = _dict_to_controller(port, ctrl_dict)

    _migrate_bindings(controllers, actions)

    return FullConfig(actions=actions, controllers=controllers)


def load_actions_from_file(path: str | Path) -> dict[str, ActionDefinition]:
    """Load only the actions from a YAML config file.

    Returns dict keyed by qualified name.  Used for import/merge.
    """
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return {}
    return _load_actions_dict(data.get("actions") or {})


def save_actions_to_file(actions: dict[str, ActionDefinition],
                         path: str | Path) -> None:
    """Save actions to a YAML file (actions section only, no controllers)."""
    data = {}
    if actions:
        data["actions"] = _actions_to_nested_dict(actions)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def save_assignments_to_file(controllers: dict[int, ControllerConfig],
                             path: str | Path) -> None:
    """Save controller assignments to a YAML file (controllers only, no actions)."""
    data = {}
    if controllers:
        data["controllers"] = {
            port: _controller_to_dict(ctrl)
            for port, ctrl in controllers.items()
        }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_assignments_from_file(path: str | Path) -> dict[int, ControllerConfig]:
    """Load only the controllers section from a YAML file.

    Returns dict keyed by port number.
    """
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return {}

    controllers = {}
    for port, ctrl_dict in (data.get("controllers") or {}).items():
        port = int(port)
        controllers[port] = _dict_to_controller(port, ctrl_dict)
    return controllers
