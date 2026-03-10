"""NtMappingMixin — shared custom NT mapping logic for managed inputs.

Provides ``mapParamToNtPath()``, ``unmap()``, ``clearMaps()``, and
``_sync_custom_maps()`` for any managed input class that defines a
``_PARAM_TYPES`` class variable mapping parameter names to their
expected Python types.

Subclasses can override ``_validate_param()`` for type-specific
checks (e.g. ManagedButton restricts threshold to BOOLEAN_TRIGGER)
and ``_get_param_value()`` / ``_set_param_value()`` when the default
``getattr``/``setattr`` pattern doesn't apply.

Design note: ``_sync_custom_maps()`` uses polling rather than ntcore
listeners because listener callbacks fire on a background thread.
Setting properties from a background thread while the main robot loop
reads them mid-pipeline would cause race conditions.  Polling once per
scheduler cycle guarantees all param changes happen at a single
deterministic point in the 20 Hz loop.
"""

import logging

import ntcore

log = logging.getLogger("InputFactory")


class NtMappingMixin:
    """Mixin providing custom NT path mapping for managed input params.

    Requires the concrete class to define:
        _PARAM_TYPES: dict[str, type]  — valid param names -> expected types

    Optionally override:
        _validate_param(param) -> str | None
            Return an error message to reject, or None to accept.
        _get_param_value(param) -> float | bool
            Read the current value (default: getattr(self, param)).
        _set_param_value(param, value) -> None
            Write a new value (default: setattr(self, param, value)).
    """

    # Subclasses must define this
    _PARAM_TYPES: dict[str, type] = {}

    def _init_nt_mapping(self) -> None:
        """Initialize custom NT mapping state. Call from __init__."""
        self._custom_nt_maps: dict[str, tuple[str, object, type]] = {}

    @property
    def mapped_params(self) -> frozenset[str]:
        """Parameter names that have active custom NT mappings.

        Used by ``sync_analog_nt()`` / ``sync_button_nt()`` to skip
        auto-generated NT sync for params controlled by a custom path.
        """
        return frozenset(self._custom_nt_maps.keys())

    def _validate_param(self, param: str) -> str | None:
        """Extra validation hook. Return error message or None."""
        return None

    def _get_param_value(self, param: str):
        """Read the current value of a parameter."""
        return getattr(self, param)

    def _set_param_value(self, param: str, value) -> None:
        """Write a new value for a parameter."""
        setattr(self, param, value)

    def mapParamToNtPath(self, nt_path: str, param: str) -> bool:
        """Map a parameter to a custom NetworkTables path.

        When the NT value at *nt_path* changes, the corresponding
        parameter is automatically updated each scheduler cycle.
        While a custom mapping is active, the auto-generated NT
        property for that parameter is ignored to prevent conflicts.

        If the entry does not exist yet, it is created with the
        current property value as the default.

        Args:
            nt_path: Full NetworkTables path to bind to
                (e.g. ``"/SmartDashboard/Drivetrain speed"``).
            param: Parameter name to control.

        Returns:
            True on success, False if *param* is invalid.
        """
        if param not in self._PARAM_TYPES:
            log.error(
                "Invalid param '%s' for %s.mapParamToNtPath. "
                "Valid params: %s",
                param, type(self).__name__,
                list(self._PARAM_TYPES.keys()))
            return False

        error = self._validate_param(param)
        if error is not None:
            log.error(error)
            return False

        expected_type = self._PARAM_TYPES[param]

        # Unmap existing if already mapped
        if param in self._custom_nt_maps:
            self.unmap(param)

        inst = ntcore.NetworkTableInstance.getDefault()
        entry = inst.getEntry(nt_path)

        # Write current value as default if entry doesn't exist yet
        current_value = self._get_param_value(param)
        if expected_type is float:
            if not entry.exists():
                entry.setDouble(float(current_value))
        elif expected_type is bool:
            if not entry.exists():
                entry.setBoolean(bool(current_value))

        self._custom_nt_maps[param] = (nt_path, entry, expected_type)
        log.info("Mapped '%s' -> NT '%s'", param, nt_path)
        return True

    def unmap(self, param: str) -> bool:
        """Remove a custom NT mapping for a parameter.

        The auto-generated NT property will resume controlling this
        param during subsequent scheduler cycles.

        Args:
            param: The parameter name to unmap.

        Returns:
            True if a mapping was removed, False if none existed.
        """
        if param not in self._custom_nt_maps:
            log.warning(
                "No custom NT mapping for param '%s' to unmap", param)
            return False

        nt_path = self._custom_nt_maps[param][0]
        del self._custom_nt_maps[param]
        log.info("Unmapped '%s' from NT '%s'", param, nt_path)
        return True

    def clearMaps(self) -> None:
        """Remove all custom NT mappings.

        All parameters return to being controlled by their
        auto-generated NT properties during subsequent scheduler cycles.
        """
        if self._custom_nt_maps:
            log.info(
                "Clearing %d custom NT mapping(s)",
                len(self._custom_nt_maps))
        self._custom_nt_maps.clear()

    def _sync_custom_maps(self) -> None:
        """Read custom NT entries and apply changed values.

        Called automatically each scheduler cycle.  Reads the NT entry
        for each custom mapping and updates the corresponding parameter
        only when the value has actually changed (to avoid unnecessary
        pipeline rebuilds).
        """
        for param, (_nt_path, entry, expected_type) in (
                self._custom_nt_maps.items()):
            current = self._get_param_value(param)
            if expected_type is float:
                nt_val = entry.getDouble(float(current))
                if nt_val != current:
                    self._set_param_value(param, nt_val)
            elif expected_type is bool:
                nt_val = entry.getBoolean(bool(current))
                if nt_val != current:
                    self._set_param_value(param, nt_val)
