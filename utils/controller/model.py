"""Shared data model for controller configuration.

Defines the dataclasses used by both the GUI tool and robot code
to represent action definitions and controller bindings.
No wpilib dependencies - pure Python.
"""

from dataclasses import dataclass, field
from enum import Enum


class TriggerMode(Enum):
    """How a button/axis action is triggered in the command-based framework."""
    ON_TRUE = "on_true"
    ON_FALSE = "on_false"
    WHILE_TRUE = "while_true"
    WHILE_FALSE = "while_false"
    TOGGLE_ON_TRUE = "toggle_on_true"
    RAW = "raw"


class InputType(Enum):
    """Type of controller input an action is designed for."""
    BUTTON = "button"
    AXIS = "axis"
    POV = "pov"
    OUTPUT = "output"


@dataclass
class ActionDefinition:
    """A named action with metadata.

    Actions are the interface between controller inputs and robot behavior.
    The `extra` dict allows forward-compatible extension without breaking
    existing configs.
    """
    name: str
    description: str = ""
    input_type: InputType = InputType.BUTTON
    trigger_mode: TriggerMode = TriggerMode.ON_TRUE
    deadband: float = 0.0
    inversion: bool = False
    scale: float = 1.0
    extra: dict = field(default_factory=dict)


@dataclass
class ControllerConfig:
    """Configuration for a single controller (port + bindings)."""
    port: int
    name: str = ""
    controller_type: str = "xbox"
    bindings: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class FullConfig:
    """Top-level configuration: action definitions + controller bindings."""
    actions: dict[str, ActionDefinition] = field(default_factory=dict)
    controllers: dict[int, ControllerConfig] = field(default_factory=dict)
