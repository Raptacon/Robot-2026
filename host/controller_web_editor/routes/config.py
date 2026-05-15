"""JSON <-> YAML round-trip for FullConfig.

The frontend never parses YAML.  Server-side, we hand off to
:mod:`utils.controller.config_io` so loading, saving, default-omission,
and legacy-format migration stay in one place.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from utils.controller.config_io import (
    CONFIG_VERSION,
    _dict_to_action,
    _dict_to_controller,
    load_config,
    save_config,
)
from utils.controller.model import (
    ActionDefinition,
    ControllerConfig,
    EventTriggerMode,
    FullConfig,
    InputType,
)


def config_to_json(config: FullConfig) -> dict:
    """Serialize FullConfig to JSON-safe primitives.

    Enums become their string values; sets become sorted lists.
    """
    actions = {}
    for qname, action in config.actions.items():
        d = asdict(action)
        d["input_type"] = action.input_type.value
        d["trigger_mode"] = action.trigger_mode.value
        actions[qname] = d

    controllers = {}
    for port, ctrl in config.controllers.items():
        controllers[str(port)] = {
            "port": ctrl.port,
            "name": ctrl.name,
            "controller_type": ctrl.controller_type,
            "bindings": {k: list(v) for k, v in ctrl.bindings.items()},
        }

    return {
        "version": config.version or CONFIG_VERSION,
        "actions": actions,
        "controllers": controllers,
        "empty_groups": sorted(config.empty_groups),
    }


def config_from_json(payload: dict) -> FullConfig:
    """Inverse of :func:`config_to_json`."""
    actions: dict[str, ActionDefinition] = {}
    for qname, raw in (payload.get("actions") or {}).items():
        group = raw.get("group", "general")
        name = raw.get("name") or qname.split(".", 1)[-1]
        action = _dict_to_action(name, raw, group=group)
        actions[action.qualified_name] = action

    controllers: dict[int, ControllerConfig] = {}
    for port_str, raw in (payload.get("controllers") or {}).items():
        port = int(port_str)
        controllers[port] = _dict_to_controller(port, raw)

    return FullConfig(
        actions=actions,
        controllers=controllers,
        empty_groups=set(payload.get("empty_groups") or []),
        version=payload.get("version") or CONFIG_VERSION,
    )


def load_as_json(path: Path) -> dict:
    """Read a YAML config file and return JSON-safe primitives."""
    return config_to_json(load_config(path))


def save_from_json(path: Path, payload: dict) -> None:
    """Write a JSON payload back to a YAML config file."""
    save_config(config_from_json(payload), path)


# Re-exported for callers that want to inspect enum vocabularies.
__all__ = [
    "EventTriggerMode",
    "InputType",
    "config_from_json",
    "config_to_json",
    "load_as_json",
    "save_from_json",
]
