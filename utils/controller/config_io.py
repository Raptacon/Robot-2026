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

No wpilib dependencies - pure Python + PyYAML.
"""

from pathlib import Path

import yaml

from .model import (
    ActionDefinition,
    BUTTON_EVENT_TRIGGER_MODES,
    ControllerConfig,
    DEFAULT_CONTROLLER_TYPE,
    DEFAULT_GROUP,
    FullConfig,
    InputType,
    EventTriggerMode,
)

# Defaults used to decide which fields to omit from YAML output
_ACTION_DEFAULTS = ActionDefinition(name="")


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
    if action.threshold != _ACTION_DEFAULTS.threshold:
        d["threshold"] = action.threshold
    if action.inversion != _ACTION_DEFAULTS.inversion:
        d["inversion"] = action.inversion
    if action.slew_rate != _ACTION_DEFAULTS.slew_rate:
        d["slew_rate"] = action.slew_rate
    if action.scale != _ACTION_DEFAULTS.scale:
        d["scale"] = action.scale
    if action.extra:
        d["extra"] = action.extra
    return d


def _dict_to_action(name: str, d: dict, group: str = DEFAULT_GROUP) -> ActionDefinition:
    """Deserialize an ActionDefinition from a YAML dict."""
    if d is None:
        d = {}
    input_type = InputType(d.get("input_type", InputType.BUTTON.value))

    # Determine appropriate default trigger mode based on input type
    if input_type in (InputType.ANALOG, InputType.VIRTUAL_ANALOG):
        default_trigger = EventTriggerMode.SCALED.value
    else:
        default_trigger = EventTriggerMode.ON_TRUE.value
    raw_trigger = d.get("trigger_mode", default_trigger)

    # Migrate button trigger modes on analog inputs to scaled
    trigger_mode = EventTriggerMode(raw_trigger)
    button_values = {m.value for m in BUTTON_EVENT_TRIGGER_MODES}
    if input_type == InputType.ANALOG and trigger_mode.value in button_values:
        trigger_mode = EventTriggerMode.SCALED

    return ActionDefinition(
        name=name,
        description=d.get("description", ""),
        group=group,
        input_type=input_type,
        trigger_mode=trigger_mode,
        deadband=float(d.get("deadband", 0.0)),
        threshold=float(d.get("threshold", 0.5)),
        inversion=bool(d.get("inversion", False)),
        slew_rate=float(d.get("slew_rate", 0.0)),
        scale=float(d.get("scale", 1.0)),
        extra=d.get("extra", {}),
    )


def _controller_to_dict(ctrl: ControllerConfig) -> dict:
    """Serialize a ControllerConfig."""
    d = {}
    if ctrl.name:
        d["name"] = ctrl.name
    if ctrl.controller_type != DEFAULT_CONTROLLER_TYPE:
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
        controller_type=d.get("controller_type", DEFAULT_CONTROLLER_TYPE),
        bindings=bindings,
    )


def _load_actions_dict(actions_data: dict
                       ) -> tuple[dict[str, ActionDefinition], set[str]]:
    """Load actions from nested (grouped) YAML format.

    Expected format::

        actions:
          group_name:
            action_name:
              description: ...

    Returns (actions_dict, empty_groups) where actions_dict is keyed by
    qualified name and empty_groups contains group names that exist but
    have no actions.
    """
    if not actions_data:
        return {}, set()

    actions = {}
    empty_groups: set[str] = set()
    for group_name, group_actions in actions_data.items():
        group_name = str(group_name)
        if not isinstance(group_actions, dict) or not group_actions:
            empty_groups.add(group_name)
            continue
        for action_name, action_dict in group_actions.items():
            action = _dict_to_action(
                str(action_name), action_dict, group=group_name)
            actions[action.qualified_name] = action

    return actions, empty_groups


def _actions_to_nested_dict(actions: dict[str, ActionDefinition],
                            empty_groups: set[str] | None = None) -> dict:
    """Group actions by group and serialize to nested dict.

    Empty groups are preserved as empty dicts so they round-trip
    through YAML save/load.
    """
    groups: dict[str, dict[str, dict]] = {}
    if empty_groups:
        for g in empty_groups:
            groups[g] = {}
    for action in actions.values():
        group = action.group
        if group not in groups:
            groups[group] = {}
        groups[group][action.name] = _action_to_dict(action)
    return groups


# --- Helpers ---

def _dump_yaml(path: str | Path, data: dict) -> None:
    """Write a data dict as YAML, creating parent directories if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# --- Public API ---

def save_config(config: FullConfig, path: str | Path) -> None:
    """Save a FullConfig to a YAML file (nested action format)."""
    data = {}

    if config.actions or config.empty_groups:
        data["actions"] = _actions_to_nested_dict(
            config.actions, config.empty_groups)

    if config.controllers:
        data["controllers"] = {
            port: _controller_to_dict(ctrl)
            for port, ctrl in config.controllers.items()
        }

    _dump_yaml(path, data)


def load_config(path: str | Path) -> FullConfig:
    """Load a FullConfig from a YAML file."""
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)

    if not data:
        return FullConfig()

    actions, empty_groups = _load_actions_dict(data.get("actions") or {})

    controllers = {}
    for port, ctrl_dict in (data.get("controllers") or {}).items():
        port = int(port)
        controllers[port] = _dict_to_controller(port, ctrl_dict)

    return FullConfig(actions=actions, controllers=controllers,
                      empty_groups=empty_groups)


def load_actions_from_file(path: str | Path) -> dict[str, ActionDefinition]:
    """Load only the actions from a YAML config file.

    Returns dict keyed by qualified name.  Used for import/merge.
    """
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return {}
    actions, _empty = _load_actions_dict(data.get("actions") or {})
    return actions


def save_actions_to_file(actions: dict[str, ActionDefinition],
                         path: str | Path) -> None:
    """Save actions to a YAML file (actions section only, no controllers)."""
    data = {}
    if actions:
        data["actions"] = _actions_to_nested_dict(actions)

    _dump_yaml(path, data)


def save_assignments_to_file(controllers: dict[int, ControllerConfig],
                             path: str | Path) -> None:
    """Save controller assignments to a YAML file (controllers only, no actions)."""
    data = {}
    if controllers:
        data["controllers"] = {
            port: _controller_to_dict(ctrl)
            for port, ctrl in controllers.items()
        }

    _dump_yaml(path, data)


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
