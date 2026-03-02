"""ManagedAnalog — shaped analog axis with runtime-adjustable properties.

Properties (deadband, inversion, scale, slew_rate) have setters that
rebuild the internal shaping pipeline closure on change.  The pipeline
is called every cycle via get() or __call__().

Pipeline order: inversion -> deadband -> curve -> scale -> slew limit

Slew rate limiting
------------------
The ``slew_rate`` property limits how fast the output can change per
second.  Set to 0 (default) to disable.  When enabled, a
``SlewRateLimiter`` is applied AFTER the shaping pipeline.

By default the same rate is used for both increasing and decreasing::

    slew_rate: 3.0   # output can change at most 3.0 units/sec up or down

To use different rates for increasing vs decreasing, add
``negative_slew_rate`` to the action's ``extra`` dict in YAML::

    general_analog_example:
      input_type: analog
      trigger_mode: scaled
      slew_rate: 5.0           # max increase rate (units/sec)
      extra:
        negative_slew_rate: -2.0  # max decrease rate (must be negative)

If ``negative_slew_rate`` is not set, it defaults to ``-slew_rate``.

Custom NT mappings
------------------
Any tunable parameter can be mapped to an arbitrary NetworkTables path
using ``mapParamToNtPath()``.  While a custom mapping is active for a
parameter, the auto-generated NT property for that parameter is ignored
(to prevent conflicts).  Changes to the custom NT value are applied
automatically each scheduler cycle::

    analog = factory.getAnalog("drivetrain.speed")
    analog.mapParamToNtPath("/SmartDashboard/Drivetrain speed", "scale")
    # Now SmartDashboard "Drivetrain speed" controls the scale property.
    analog.unmap("scale")      # Revert to auto-generated NT control
    analog.clearMaps()         # Remove all custom mappings
"""

from typing import Callable

from utils.controller.model import ActionDefinition, EventTriggerMode
from utils.input._nt_mapping import NtMappingMixin
from utils.input.shaping import build_shaping_pipeline


class ManagedAnalog(NtMappingMixin):
    """A managed analog input with full shaping pipeline.

    Args:
        action: The ActionDefinition this analog represents (may be None).
        accessor: Callable returning the raw axis value each cycle.
        default_value: Value returned when no accessor is bound.
    """

    _PARAM_TYPES: dict[str, type] = {
        "deadband": float,
        "inversion": bool,
        "scale": float,
        "slew_rate": float,
    }

    def __init__(
        self,
        action: ActionDefinition | None,
        accessor: Callable[[], float],
        default_value: float = 0.0,
    ):
        self._action = action
        self._accessor = accessor
        self._default_value = default_value

        # Mutable properties — initialized from action or defaults
        if action is not None:
            self._deadband = action.deadband
            self._inversion = action.inversion
            self._scale = action.scale
            self._slew_rate = action.slew_rate
            self._trigger_mode = action.trigger_mode
            self._extra = action.extra or {}
        else:
            self._deadband = 0.0
            self._inversion = False
            self._scale = 1.0
            self._slew_rate = 0.0
            self._trigger_mode = EventTriggerMode.RAW
            self._extra = {}

        self._init_nt_mapping()

        self._pipeline: Callable[[float], float] = lambda x: x
        self._slew_limiter = None
        self._rebuild_pipeline()
        self._rebuild_slew_limiter()

    # --- Properties with pipeline rebuild ---

    @property
    def deadband(self) -> float:
        return self._deadband

    @deadband.setter
    def deadband(self, value: float) -> None:
        if self._deadband != value:
            self._deadband = value
            self._rebuild_pipeline()

    @property
    def inversion(self) -> bool:
        return self._inversion

    @inversion.setter
    def inversion(self, value: bool) -> None:
        if self._inversion != value:
            self._inversion = value
            self._rebuild_pipeline()

    @property
    def scale(self) -> float:
        return self._scale

    @scale.setter
    def scale(self, value: float) -> None:
        if self._scale != value:
            self._scale = value
            self._rebuild_pipeline()

    @property
    def slew_rate(self) -> float:
        """Max output change rate in units/sec.  0 = disabled.

        Applies symmetrically (same limit up and down) unless
        ``extra["negative_slew_rate"]`` is set on the action.
        """
        return self._slew_rate

    @slew_rate.setter
    def slew_rate(self, value: float) -> None:
        if self._slew_rate != value:
            self._slew_rate = value
            self._rebuild_slew_limiter()

    @property
    def action(self) -> ActionDefinition | None:
        return self._action

    # --- Value access ---

    def get(self) -> float:
        """Return the shaped value through the full pipeline + slew limit."""
        shaped = self._pipeline(self._accessor())
        if self._slew_limiter is not None:
            shaped = self._slew_limiter.calculate(shaped)
        return shaped

    def getRaw(self) -> float:
        """Return the unmodified raw HID value."""
        return self._accessor()

    def __call__(self) -> float:
        """Alias for get() — makes ManagedAnalog a Callable[[], float]."""
        return self.get()

    # --- Internal ---

    def _rebuild_pipeline(self) -> None:
        """Rebuild the shaping closure from current properties."""
        self._pipeline = build_shaping_pipeline(
            inversion=self._inversion,
            deadband=self._deadband,
            trigger_mode=self._trigger_mode,
            scale=self._scale,
            extra=self._extra,
        )

    def _rebuild_slew_limiter(self) -> None:
        """Recreate the SlewRateLimiter when rate changes.

        SlewRateLimiter rate limits are constructor params, so a new
        instance is needed when the rate changes.  Setting slew_rate
        to 0 disables the limiter.

        The negative (decreasing) rate defaults to ``-slew_rate`` but
        can be overridden via ``extra["negative_slew_rate"]`` in the
        action's YAML config for asymmetric limiting.
        """
        if self._slew_rate <= 0:
            self._slew_limiter = None
            return
        try:
            from wpimath.filter import SlewRateLimiter
            neg_rate = self._extra.get(
                "negative_slew_rate", -self._slew_rate)
            self._slew_limiter = SlewRateLimiter(
                self._slew_rate, neg_rate, 0.0)
        except ImportError:
            # Graceful degradation in test environments
            self._slew_limiter = None

    def _rebind(self, accessor: Callable[[], float]) -> None:
        """Swap the raw accessor for dynamic remapping."""
        self._accessor = accessor
