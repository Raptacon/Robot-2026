"""Shared data model for controller configuration.

Defines the dataclasses used by both the GUI tool and robot code
to represent action definitions and controller bindings.
No wpilib dependencies - pure Python.
"""

from dataclasses import dataclass, field
from enum import Enum


class TriggerMode(Enum):
    """How a button/analog action is triggered or shaped.

    Button modes control when commands fire.
    Analog modes control how the analog value is shaped/curved.
    """
    # Button modes
    ON_TRUE = "on_true"
    ON_FALSE = "on_false"
    WHILE_TRUE = "while_true"
    WHILE_FALSE = "while_false"
    TOGGLE_ON_TRUE = "toggle_on_true"
    # Analog response curves
    RAW = "raw"
    SCALED = "scaled"
    SQUARED = "squared"
    SEGMENTED = "segmented"
    SPLINE = "spline"


# Which trigger modes apply to which input types
BUTTON_TRIGGER_MODES = [
    TriggerMode.ON_TRUE,
    TriggerMode.ON_FALSE,
    TriggerMode.WHILE_TRUE,
    TriggerMode.WHILE_FALSE,
    TriggerMode.TOGGLE_ON_TRUE,
]
ANALOG_TRIGGER_MODES = [
    TriggerMode.SCALED,
    TriggerMode.SQUARED,
    TriggerMode.RAW,
    TriggerMode.SEGMENTED,
    TriggerMode.SPLINE,
]


class InputType(Enum):
    """Type of controller input an action is designed for."""
    BUTTON = "button"
    ANALOG = "analog"
    POV = "pov"
    OUTPUT = "output"


@dataclass
class ActionDefinition:
    """A named action with metadata.

    Actions are the interface between controller inputs and robot behavior.
    The `extra` dict allows forward-compatible extension without breaking
    existing configs.

    Actions belong to a group (default "general"). The fully qualified name
    is ``group.name`` (e.g. ``intake.run``, ``shooter.fire``).
    """
    name: str
    description: str = ""
    group: str = "general"
    input_type: InputType = InputType.BUTTON
    trigger_mode: TriggerMode = TriggerMode.ON_TRUE
    deadband: float = 0.0
    inversion: bool = False
    scale: float = 1.0
    extra: dict = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """Return the fully qualified name: group.name."""
        return f"{self.group}.{self.name}"


def parse_qualified_name(qualified: str) -> tuple[str, str]:
    """Split a qualified name into (group, short_name).

    If there is no dot, returns ('general', qualified).
    """
    if '.' in qualified:
        group, _, name = qualified.partition('.')
        return group, name
    return 'general', qualified


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
    empty_groups: set[str] = field(default_factory=set)
