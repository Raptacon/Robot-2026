# Native imports
import importlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

# Third-party imports
from ntcore.util import ntproperty


logger = logging.getLogger(__name__)


class SubsystemState(str, Enum):
    """Persistent state for a subsystem entry."""
    enabled = "enabled"
    disabled = "disabled"
    required = "required"


@dataclass
class SubsystemEntry:
    """
    Declares a subsystem for registration with SubsystemRegistry.

    Args:
        name: unique ID (e.g. "drivetrain", "turret")
        default_state: used if no persisted NT value exists
        creator: callable that creates and returns the subsystem instance;
                 receives a dict of {name: instance} for already-created subsystems
        dependencies: names of subsystems that must exist first
    """
    name: str
    default_state: SubsystemState
    creator: Callable[[Dict[str, Any]], Any]
    dependencies: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Global self-registration registry
# ---------------------------------------------------------------------------
_global_registry: List[SubsystemEntry] = []


def register_subsystem(
    name: str,
    default_state: SubsystemState,
    creator: Callable[[Dict[str, Any]], Any],
    dependencies: Optional[List[str]] = None,
) -> None:
    """Register a subsystem entry into the global registry (called at module level)."""
    _global_registry.append(SubsystemEntry(
        name=name,
        default_state=default_state,
        creator=creator,
        dependencies=dependencies or [],
    ))


def get_registered_entries() -> List[SubsystemEntry]:
    """Return a copy of all globally registered subsystem entries."""
    return list(_global_registry)


def clear_registry() -> None:
    """Clear all globally registered entries (useful for testing)."""
    _global_registry.clear()


# ---------------------------------------------------------------------------
# NT persistence helpers
# ---------------------------------------------------------------------------
# Cache of dynamically-created classes for NT persistence per subsystem name
_registry_state_classes: Dict[str, type] = {}


def _get_state_holder(name: str) -> Any:
    """
    Get or create a singleton class with an ntproperty for the given
    subsystem name. Uses the same dynamic-class-with-ntproperty pattern
    as PositionCalibration to get persistent NT storage per subsystem.

    Returns an instance whose `.state` attribute is an ntproperty
    backed by `/subsystem/<name>`.
    """
    if name not in _registry_state_classes:
        attrs = {
            "state": ntproperty(
                f"/subsystem/{name}", "",
                writeDefault=False, persistent=True
            ),
        }
        cls = type(
            f"_SubsystemNTState_{name}",
            (),
            attrs,
        )
        _registry_state_classes[name] = cls()
    return _registry_state_classes[name]


class SubsystemFactory:
    """Handles creation of a single subsystem with error isolation."""

    @staticmethod
    def create(
        entry: SubsystemEntry,
        state: SubsystemState,
        created_subsystems: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """
        Create a subsystem based on its entry and resolved state.

        Args:
            entry: the subsystem declaration
            state: the resolved state (after NT override)
            created_subsystems: dict of already-created subsystems passed to the creator

        Returns:
            The created subsystem instance, or None if disabled or
            if an enabled (non-required) subsystem fails to create.

        Raises:
            RuntimeError: if a required subsystem fails to create
        """
        if state == SubsystemState.disabled:
            logger.info("Subsystem '%s' is disabled, skipping creation", entry.name)
            return None

        subs = created_subsystems if created_subsystems is not None else {}

        try:
            subsystem = entry.creator(subs)
            logger.info("Subsystem '%s' created successfully", entry.name)
            return subsystem
        except Exception as e:
            if state == SubsystemState.required:
                raise RuntimeError(
                    f"Required subsystem '{entry.name}' failed to create: {e}"
                ) from e
            else:
                logger.error(
                    "Subsystem '%s' failed to create (non-fatal): %s",
                    entry.name, e, exc_info=True
                )
                return None


class SubsystemRegistry:
    """
    Processes an ordered manifest of SubsystemEntry items.

    Resolves each entry's state from NT persistence (falling back to
    the entry's default_state), checks dependencies, creates subsystems
    via SubsystemFactory, and stores the results for lifecycle management.

    Convention-based lifecycle:
    - Controls: auto-discovers commands/{name}_controls.py and calls register_controls(sub, container)
    - Telemetry: calls sub.updateTelemetry() if the method exists
    - Disabled init: calls sub.onDisabledInit() if the method exists
    """

    def __init__(self, manifest: List[SubsystemEntry], container: Any = None) -> None:
        self._entries: Dict[str, SubsystemEntry] = {}
        self._subsystems: Dict[str, Optional[Any]] = {}
        self._active_entries: List[SubsystemEntry] = []
        self._container = container

        for entry in manifest:
            self._entries[entry.name] = entry
            state = self._resolve_state(entry)
            self._publish_state(entry.name, state)

            # Check dependencies
            if state != SubsystemState.disabled:
                missing_deps = [
                    dep for dep in entry.dependencies
                    if dep not in self._subsystems or self._subsystems[dep] is None
                ]
                if missing_deps:
                    logger.warning(
                        "Subsystem '%s' skipped: missing dependencies %s",
                        entry.name, missing_deps
                    )
                    self._subsystems[entry.name] = None
                    continue

            subsystem = SubsystemFactory.create(entry, state, self._subsystems)
            self._subsystems[entry.name] = subsystem

            if subsystem is not None:
                self._active_entries.append(entry)

    def get(self, name: str) -> Optional[Any]:
        """Retrieve a subsystem by name. Returns None if not created."""
        return self._subsystems.get(name)

    @property
    def active_subsystems(self) -> Dict[str, Any]:
        """Return {name: instance} for all successfully created subsystems."""
        return {
            entry.name: self._subsystems[entry.name]
            for entry in self._active_entries
        }

    def _call_controls_hook(self, hook_name: str) -> None:
        """Call a named function from each active subsystem's controls module."""
        for entry in self._active_entries:
            subsystem = self._subsystems[entry.name]
            mod = self._controls_modules.get(entry.name)
            if mod is None:
                continue
            fn = getattr(mod, hook_name, None)
            if fn is None:
                continue
            try:
                fn(subsystem, self._container)
            except Exception as e:
                logger.error(
                    "%s failed for '%s': %s",
                    hook_name, entry.name, e, exc_info=True
                )

    def register_all_controls(self) -> None:
        """Auto-discover controls modules and call register_controls for each active subsystem."""
        self._controls_modules: Dict[str, Any] = {}
        for entry in self._active_entries:
            try:
                mod = importlib.import_module(f"commands.{entry.name}_controls")
                self._controls_modules[entry.name] = mod
            except ImportError:
                # No controls file for this subsystem — that's fine
                continue
            except Exception as e:
                logger.error(
                    "Failed to import controls for '%s': %s",
                    entry.name, e, exc_info=True
                )
                continue

            subsystem = self._subsystems[entry.name]
            try:
                mod.register_controls(subsystem, self._container)
            except Exception as e:
                logger.error(
                    "Failed to register controls for '%s': %s",
                    entry.name, e, exc_info=True
                )

    def run_all_teleop_init(self) -> None:
        """Call teleop_init() from each active subsystem's controls module."""
        self._call_controls_hook("teleop_init")

    def run_all_teleop_periodic(self) -> None:
        """Call teleop_periodic() from each active subsystem's controls module."""
        self._call_controls_hook("teleop_periodic")

    def run_all_telemetry(self) -> None:
        """Call updateTelemetry() on each active subsystem that has it."""
        for entry in self._active_entries:
            subsystem = self._subsystems[entry.name]
            if hasattr(subsystem, 'updateTelemetry'):
                try:
                    subsystem.updateTelemetry()
                except Exception as e:
                    logger.error(
                        "Telemetry update failed for '%s': %s",
                        entry.name, e, exc_info=True
                    )

    def run_all_disabled_init(self) -> None:
        """Call onDisabledInit() on each active subsystem that has it."""
        for entry in self._active_entries:
            subsystem = self._subsystems[entry.name]
            if hasattr(subsystem, 'onDisabledInit'):
                try:
                    subsystem.onDisabledInit()
                except Exception as e:
                    logger.error(
                        "Disabled init failed for '%s': %s",
                        entry.name, e, exc_info=True
                    )

    def _resolve_state(self, entry: SubsystemEntry) -> SubsystemState:
        """
        Resolve the effective state for an entry. Reads from NT persistence
        first; falls back to the entry's default_state if no persisted value
        or if the persisted value is invalid.
        """
        holder = _get_state_holder(entry.name)
        nt_value = holder.state

        if nt_value:
            try:
                return SubsystemState(nt_value)
            except ValueError:
                logger.warning(
                    "Invalid NT state '%s' for subsystem '%s', using default '%s'",
                    nt_value, entry.name, entry.default_state.value
                )

        return entry.default_state

    def _publish_state(self, name: str, state: SubsystemState) -> None:
        """Write the resolved state back to NT so it's visible in the dashboard."""
        holder = _get_state_holder(name)
        holder.state = state.value
