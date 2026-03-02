"""Shared data model for controller configuration.

Defines the dataclasses used by both the GUI tool and robot code
to represent action definitions and controller bindings.
No wpilib dependencies - pure Python.
"""

from dataclasses import dataclass, field
from enum import Enum


class EventTriggerMode(Enum):
    """How a button/analog action is triggered or shaped.

    Button modes control when commands fire via ``commands2.button.Trigger``
    bindings (not to be confused with the Xbox "trigger" — the analog
    left_trigger / right_trigger inputs).  Each mode maps to a Trigger
    binding method: ON_TRUE -> ``.onTrue()``, WHILE_TRUE -> ``.whileTrue()``,
    etc.

    Analog modes control how the analog value is shaped/curved before
    it reaches the subsystem.
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
BUTTON_EVENT_TRIGGER_MODES = [
    EventTriggerMode.ON_TRUE,
    EventTriggerMode.ON_FALSE,
    EventTriggerMode.WHILE_TRUE,
    EventTriggerMode.WHILE_FALSE,
    EventTriggerMode.TOGGLE_ON_TRUE,
]
ANALOG_EVENT_TRIGGER_MODES = [
    EventTriggerMode.SCALED,
    EventTriggerMode.SQUARED,
    EventTriggerMode.RAW,
    EventTriggerMode.SEGMENTED,
    EventTriggerMode.SPLINE,
]


class InputType(Enum):
    """Type of controller input an action is designed for.

    BOOLEAN_TRIGGER converts an analog axis (e.g. left_trigger) into a
    boolean using a threshold comparison — not related to
    ``commands2.button.Trigger``.
    """
    BUTTON = "button"
    ANALOG = "analog"
    POV = "pov"
    OUTPUT = "output"
    BOOLEAN_TRIGGER = "boolean_trigger"
    VIRTUAL_ANALOG = "virtual_analog"


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
    trigger_mode: EventTriggerMode = EventTriggerMode.ON_TRUE
    deadband: float = 0.0
    threshold: float = 0.5     # For BOOLEAN_TRIGGER: axis > threshold = True
    inversion: bool = False
    slew_rate: float = 0.0  # Max output change rate (units/sec), 0 = disabled.
    # Symmetric by default. For asymmetric, set
    # extra["negative_slew_rate"] to a negative value.
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
