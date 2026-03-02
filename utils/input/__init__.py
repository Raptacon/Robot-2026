"""Controller input factory — config-driven managed input objects.

Public API::

    from utils.input import InputFactory, get_factory

    # In robotInit — create the factory (registers as active):
    factory = InputFactory(config_path="data/controller.yaml")

    # Anywhere else — fetch the active factory:
    factory = get_factory()
    button = factory.getButton("intake.run")
    analog = factory.getAnalog("drivetrain.speed")
    rumble = factory.getRumbleControl("general.rumble_left")
"""

from utils.input.factory import InputFactory, get_factory
from utils.input.managed_analog import ManagedAnalog
from utils.input.managed_button import ManagedButton
from utils.input.managed_rumble import ManagedRumble
from utils.input.validation import ValidationIssue, validate_config

__all__ = [
    "InputFactory",
    "get_factory",
    "ManagedAnalog",
    "ManagedButton",
    "ManagedRumble",
    "ValidationIssue",
    "validate_config",
]
