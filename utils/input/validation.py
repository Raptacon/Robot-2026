"""Config validation and error reporting for controller configurations.

Checks type consistency, input name validity, curve data integrity,
and other structural rules.  Returns a list of ValidationIssue objects.
"""

from dataclasses import dataclass

from utils.controller.model import (
    ANALOG_EVENT_TRIGGER_MODES,
    BUTTON_EVENT_TRIGGER_MODES,
    ActionDefinition,
    FullConfig,
    InputType,
    EventTriggerMode,
)
from utils.input.xbox_map import ALL_INPUT_NAMES, get_input_category


@dataclass
class ValidationIssue:
    """A single validation finding."""
    level: str       # "error" or "warning"
    message: str
    context: str = ""

    def __str__(self) -> str:
        prefix = f"[{self.level.upper()}]"
        if self.context:
            return f"{prefix} {self.context}: {self.message}"
        return f"{prefix} {self.message}"


def _validate_action(action: ActionDefinition) -> list[ValidationIssue]:
    """Validate a single action definition (without binding context)."""
    issues = []
    qn = action.qualified_name

    # EventTriggerMode / InputType compatibility
    if action.input_type == InputType.ANALOG:
        if action.trigger_mode in BUTTON_EVENT_TRIGGER_MODES:
            issues.append(ValidationIssue(
                "warning",
                f"Analog action uses button trigger mode "
                f"'{action.trigger_mode.value}'",
                qn))

    elif action.input_type in (InputType.BUTTON, InputType.POV):
        if action.trigger_mode in ANALOG_EVENT_TRIGGER_MODES:
            issues.append(ValidationIssue(
                "warning",
                f"Button/POV action uses analog trigger mode "
                f"'{action.trigger_mode.value}'",
                qn))

    elif action.input_type == InputType.BOOLEAN_TRIGGER:
        if action.trigger_mode not in BUTTON_EVENT_TRIGGER_MODES:
            issues.append(ValidationIssue(
                "error",
                f"BOOLEAN_TRIGGER must use a button trigger mode, "
                f"got '{action.trigger_mode.value}'",
                qn))

    elif action.input_type == InputType.VIRTUAL_ANALOG:
        if action.trigger_mode not in ANALOG_EVENT_TRIGGER_MODES:
            issues.append(ValidationIssue(
                "error",
                f"VIRTUAL_ANALOG must use an analog trigger mode, "
                f"got '{action.trigger_mode.value}'",
                qn))

    # Spline / segmented curve data validation
    if action.trigger_mode == EventTriggerMode.SPLINE:
        pts = (action.extra or {}).get("spline_points")
        if not pts:
            issues.append(ValidationIssue(
                "error",
                "Spline trigger mode requires 'spline_points' in extra",
                qn))
        elif isinstance(pts, list):
            if len(pts) < 2:
                issues.append(ValidationIssue(
                    "error", "Spline needs at least 2 points", qn))
            for i, p in enumerate(pts):
                if not isinstance(p, dict):
                    issues.append(ValidationIssue(
                        "error", f"Spline point {i} is not a dict", qn))
                    continue
                for key in ("x", "y", "tangent"):
                    if key not in p:
                        issues.append(ValidationIssue(
                            "error",
                            f"Spline point {i} missing '{key}'",
                            qn))
            # Check sorted by x
            if (len(pts) >= 2
                    and all(isinstance(p, dict) and "x" in p for p in pts)):
                xs = [p["x"] for p in pts]
                if xs != sorted(xs):
                    issues.append(ValidationIssue(
                        "warning",
                        "Spline points not sorted by x",
                        qn))

    if action.trigger_mode == EventTriggerMode.SEGMENTED:
        pts = (action.extra or {}).get("segment_points")
        if not pts:
            issues.append(ValidationIssue(
                "error",
                "Segmented trigger mode requires "
                "'segment_points' in extra",
                qn))
        elif isinstance(pts, list):
            if len(pts) < 2:
                issues.append(ValidationIssue(
                    "error", "Segments need at least 2 points", qn))
            for i, p in enumerate(pts):
                if not isinstance(p, dict):
                    issues.append(ValidationIssue(
                        "error", f"Segment point {i} is not a dict", qn))
                    continue
                for key in ("x", "y"):
                    if key not in p:
                        issues.append(ValidationIssue(
                            "error",
                            f"Segment point {i} missing '{key}'",
                            qn))
            # Check sorted by x
            if (len(pts) >= 2
                    and all(isinstance(p, dict) and "x" in p for p in pts)):
                xs = [p["x"] for p in pts]
                if xs != sorted(xs):
                    issues.append(ValidationIssue(
                        "warning",
                        "Segment points not sorted by x",
                        qn))

    return issues


def validate_config(config: FullConfig) -> list[ValidationIssue]:
    """Validate a full controller configuration.

    Returns a list of issues (errors and warnings).
    An empty list means the config is valid.
    """
    issues: list[ValidationIssue] = []

    # Validate each action definition
    for action in config.actions.values():
        issues.extend(_validate_action(action))

    # Validate controller bindings
    for port, ctrl in config.controllers.items():
        ctrl_ctx = f"controller {port} ({ctrl.name or 'unnamed'})"

        for input_name, action_names in ctrl.bindings.items():
            # Check input name is recognized
            if input_name not in ALL_INPUT_NAMES:
                issues.append(ValidationIssue(
                    "error",
                    f"Unknown input name '{input_name}'",
                    ctrl_ctx))

            category = get_input_category(input_name)

            for action_name in action_names:
                # Check action exists
                if action_name not in config.actions:
                    issues.append(ValidationIssue(
                        "error",
                        f"Binding references unknown action "
                        f"'{action_name}'",
                        f"{ctrl_ctx} / {input_name}"))
                    continue

                action = config.actions[action_name]

                # Type consistency: action input_type vs physical input
                if (action.input_type == InputType.ANALOG
                        and category == "button"):
                    issues.append(ValidationIssue(
                        "warning",
                        f"Analog action '{action_name}' bound to "
                        f"button input '{input_name}'",
                        ctrl_ctx))

                if (action.input_type in (InputType.BUTTON, InputType.POV)
                        and category == "axis"):
                    issues.append(ValidationIssue(
                        "warning",
                        f"Button/POV action '{action_name}' bound to "
                        f"axis input '{input_name}'",
                        ctrl_ctx))

                if (action.input_type == InputType.BOOLEAN_TRIGGER
                        and category != "axis"):
                    issues.append(ValidationIssue(
                        "error",
                        f"BOOLEAN_TRIGGER action '{action_name}' must "
                        f"be bound to an axis input, got '{input_name}'",
                        ctrl_ctx))

                if (action.input_type == InputType.VIRTUAL_ANALOG
                        and category not in ("button", "pov")):
                    issues.append(ValidationIssue(
                        "error",
                        f"VIRTUAL_ANALOG action '{action_name}' must "
                        f"be bound to a button/POV input, "
                        f"got '{input_name}'",
                        ctrl_ctx))

                if (action.input_type == InputType.OUTPUT
                        and category != "output"):
                    issues.append(ValidationIssue(
                        "warning",
                        f"Output action '{action_name}' bound to "
                        f"non-output input '{input_name}'",
                        ctrl_ctx))

    # Warn about empty action definitions
    for action in config.actions.values():
        if (not action.description
                and action.input_type == InputType.BUTTON
                and action.trigger_mode == EventTriggerMode.ON_TRUE
                and action.deadband == 0.0
                and action.scale == 1.0
                and not action.extra):
            issues.append(ValidationIssue(
                "warning",
                "Action has all default values (possibly empty definition)",
                action.qualified_name))

    return issues
