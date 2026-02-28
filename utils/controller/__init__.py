"""Controller configuration utilities.

Shared between the host GUI tool and robot code.
"""

from .config_io import load_config, save_config
from .model import (
    ActionDefinition,
    ControllerConfig,
    FullConfig,
    InputType,
    TriggerMode,
)

__all__ = [
    "ActionDefinition",
    "ControllerConfig",
    "FullConfig",
    "InputType",
    "TriggerMode",
    "load_config",
    "save_config",
]
