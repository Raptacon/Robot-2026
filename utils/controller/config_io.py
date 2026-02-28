"""YAML load/save for controller configuration.

Handles serialization of FullConfig to/from human-readable YAML.
Omits default values for cleaner output and preserves unknown fields
in the `extra` dict for forward compatibility.

No wpilib dependencies - pure Python + PyYAML.
"""

from pathlib import Path

import yaml

from .model import (
    ActionDefinition,
    ControllerConfig,
    FullConfig,
    InputType,
    TriggerMode,
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
    if action.inversion != _ACTION_DEFAULTS.inversion:
        d["inversion"] = action.inversion
    if action.scale != _ACTION_DEFAULTS.scale:
        d["scale"] = action.scale
    if action.extra:
        d["extra"] = action.extra
    return d


def _dict_to_action(name: str, d: dict) -> ActionDefinition:
    """Deserialize an ActionDefinition from a YAML dict."""
    if d is None:
        d = {}
    return ActionDefinition(
        name=name,
        description=d.get("description", ""),
        input_type=InputType(d.get("input_type", InputType.BUTTON.value)),
        trigger_mode=TriggerMode(d.get("trigger_mode", TriggerMode.ON_TRUE.value)),
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


def save_config(config: FullConfig, path: str | Path) -> None:
    """Save a FullConfig to a YAML file."""
    data = {}

    if config.actions:
        data["actions"] = {
            name: _action_to_dict(action)
            for name, action in config.actions.items()
        }

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
    """Load a FullConfig from a YAML file."""
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)

    if not data:
        return FullConfig()

    actions = {}
    for name, action_dict in (data.get("actions") or {}).items():
        actions[name] = _dict_to_action(name, action_dict)

    controllers = {}
    for port, ctrl_dict in (data.get("controllers") or {}).items():
        port = int(port)
        controllers[port] = _dict_to_controller(port, ctrl_dict)

    return FullConfig(actions=actions, controllers=controllers)
