# Native imports
import math
from typing import Any, Callable, Optional

# Third-party imports
import wpilib
from ntcore.util import ntproperty


# Cache of dynamically-created subclasses keyed by mechanism name.
# Each subclass has ntproperty descriptors with NT paths unique to
# that mechanism, so multiple PositionCalibration instances with
# different names get independent persistent storage.
_calibration_classes = {}

# Valid callback names accepted by the constructor and set_callbacks()
_VALID_CALLBACKS = {
    'get_position', 'get_velocity', 'set_position',
    'set_motor_output', 'stop_motor',
    'set_current_limit', 'set_soft_limits', 'disable_soft_limits',
    'save_config', 'restore_config',
    'get_forward_limit_switch', 'get_reverse_limit_switch',
    'on_limit_detected',
}

# Callbacks that must always be set before homing or calibration
_CORE_REQUIRED = {'set_motor_output', 'stop_motor', 'set_position'}


class PositionCalibration:
    """
    Reusable calibration and homing controller for positional mechanisms.

    Extracts sensorless or sensor homing and two-phase calibration logic
    from mechanism-specific subsystems into a standalone, motor-agnostic
    class. All hardware interaction is done through user-provided
    callbacks, making this compatible with any motor controller.

    For SparkMax users, the ``motor`` convenience parameter auto-populates
    callbacks via SparkMaxCallbacks. Individual callbacks passed as keyword
    arguments override the SparkMax defaults.

    Calibration discovers mechanical hard limits by driving into stops,
    then computes soft limits with a configurable safety margin. Persists
    discovered limits to NetworkTables via ntproperty so values survive
    reboots.

    ## Callbacks

    **Core required** (must be set before homing or calibration):

    | Name | Signature | Purpose |
    |------|-----------|---------|
    | `set_motor_output` | `(float) -> None` | Drive motor at duty cycle (-1.0 to 1.0) |
    | `stop_motor` | `() -> None` | Stop motor output |
    | `set_position` | `(float) -> None` | Reset encoder position |

    **Detection** (at least one required per homing direction):

    | Name | Signature | Purpose |
    |------|-----------|---------|
    | `get_velocity` | `() -> float` | Enables stall detection |
    | `get_forward_limit_switch` | `() -> bool` | Forward limit switch |
    | `get_reverse_limit_switch` | `() -> bool` | Reverse limit switch |

    **Optional** (enhance safety/features but not required):

    | Name | Signature | Purpose |
    |------|-----------|---------|
    | `get_position` | `() -> float` | Required only for calibration phase 2 |
    | `set_current_limit` | `(float) -> None` | Protective current limit during homing |
    | `set_soft_limits` | `(min, max) -> None` | Apply soft limits to hardware |
    | `disable_soft_limits` | `(fwd, rev) -> None` | Disable soft limits for free travel |
    | `save_config` | `() -> Any` | Snapshot motor config before homing |
    | `restore_config` | `(Any) -> None` | Restore snapshot after homing |
    | `on_limit_detected` | `(pos, dir) -> None` | Fires when a hard limit is found |

    Use ``get_callbacks()`` to inspect the current callback dict (returns
    ``None`` for any callback that has not been set).

    Examples
    --------

    SparkMax convenience (auto-generates all callbacks)::

        self.calibration = PositionCalibration(
            name="Turret",
            fallback_min=-90, fallback_max=90,
            motor=self.motor, encoder=self.encoder)

    Pure callbacks with stall detection only::

        self.calibration = PositionCalibration(
            name="Elevator",
            fallback_min=0.0, fallback_max=1.5,
            set_motor_output=lambda pct: motor.set(pct),
            stop_motor=lambda: motor.stopMotor(),
            set_position=lambda v: encoder.setPosition(v),
            get_velocity=lambda: encoder.getVelocity())

    Pure callbacks with limit switches only::

        self.calibration = PositionCalibration(
            name="Arm",
            fallback_min=0.0, fallback_max=90.0,
            set_motor_output=lambda pct: motor.set(pct),
            stop_motor=lambda: motor.stopMotor(),
            set_position=lambda v: encoder.setPosition(v),
            get_forward_limit_switch=lambda: fwd_switch.get(),
            get_reverse_limit_switch=lambda: rev_switch.get())

    Deferred setup (set callbacks after construction)::

        cal = PositionCalibration(
            name="Wrist",
            fallback_min=-45, fallback_max=45)
        # ... later, once hardware is ready ...
        cal.set_callbacks(
            set_motor_output=motor.set,
            stop_motor=motor.stopMotor,
            set_position=encoder.setPosition,
            get_velocity=encoder.getVelocity)
    """

    # -- Callback type declarations --
    _cb_get_position: Optional[Callable[[], float]]
    _cb_get_velocity: Optional[Callable[[], float]]
    _cb_set_position: Optional[Callable[[float], None]]
    _cb_set_motor_output: Optional[Callable[[float], None]]
    _cb_stop_motor: Optional[Callable[[], None]]
    _cb_set_current_limit: Optional[Callable[[float], None]]
    _cb_set_soft_limits: Optional[Callable[[float, float], None]]
    _cb_disable_soft_limits: Optional[Callable[[bool, bool], None]]
    _cb_save_config: Optional[Callable[[], Any]]
    _cb_restore_config: Optional[Callable[[Any], None]]
    _cb_get_forward_limit_switch: Optional[Callable[[], bool]]
    _cb_get_reverse_limit_switch: Optional[Callable[[], bool]]
    _cb_on_limit_detected: Optional[Callable[[float, str], None]]

    def __init__(
        self,
        name: str,
        fallback_min: float,
        fallback_max: float,
        *,
        motor=None,
        encoder=None,
        **kwargs,
    ) -> None:
        """
        Create a new PositionCalibration controller.

        Args:
            name: mechanism name used for NT paths and alerts (e.g. "Turret")
            fallback_min: reverse soft limit used before calibration data
                exists. Once calibrated, the persisted hard limits are used
                instead. The caller is responsible for the far end of travel
                if only homing (not full calibration) is performed.
            fallback_max: forward soft limit used before calibration data
                exists. See fallback_min for details.
            motor: (optional) rev.SparkMax for convenience callback generation
            encoder: (optional) rev.RelativeEncoder (defaults to motor.getEncoder())
            **kwargs: callback overrides (see _VALID_CALLBACKS for valid keys)
        """
        # Assign this instance to a cached subclass with ntproperty
        # descriptors keyed to this mechanism's name. ntproperty is a
        # class-level descriptor, so each mechanism name needs its own
        # class to avoid key collisions. The cache ensures the
        # ntproperty is created only once per name so defaults don't
        # overwrite previously persisted values.
        if name not in _calibration_classes:
            prefix = f"/{name}/calibration"
            attrs = {
                "_nt_hard_limit_min": ntproperty(
                    f"{prefix}/hard_limit_min", float("nan"),
                    writeDefault=False, persistent=True),
                "_nt_hard_limit_max": ntproperty(
                    f"{prefix}/hard_limit_max", float("nan"),
                    writeDefault=False, persistent=True),
                "_nt_soft_limit_margin": ntproperty(
                    f"{prefix}/soft_limit_margin", 0.05,
                    writeDefault=False, persistent=True),
            }
            # Non-persistent booleans for callback status
            for cb_name in sorted(_VALID_CALLBACKS):
                attrs[f"_nt_cb_{cb_name}"] = ntproperty(
                    f"{prefix}/callbacks/{cb_name}", False,
                    writeDefault=True, persistent=False)
            _calibration_classes[name] = type(
                f"PositionCalibration_{name}",
                (PositionCalibration,),
                attrs,
            )
        self.__class__ = _calibration_classes[name]

        self._name = name

        # Soft limits — initialized to defaults, overwritten by
        # _load_from_nt() if persisted calibration data exists
        self._min_soft_limit = fallback_min
        self._max_soft_limit = fallback_max

        # Calibration state
        self._hard_limit_min = None
        self._hard_limit_max = None
        self._is_calibrated = False
        self._is_calibrating = False
        self._calibration_phase = 0
        self._soft_limit_margin = 0.05
        self._position_offset = 0.0

        # Homing state
        self._is_homing = False
        self._saved_config = None

        # -- Build callbacks --
        # Validate kwargs keys
        unknown = set(kwargs.keys()) - _VALID_CALLBACKS
        if unknown:
            raise ValueError(
                f"Unknown callback(s): {', '.join(sorted(unknown))}"
            )

        # If motor provided, generate SparkMax defaults
        defaults = {}
        if motor is not None:
            from utils.spark_max_callbacks import SparkMaxCallbacks
            defaults = SparkMaxCallbacks(motor, encoder).as_dict()

        # Merge: explicit kwargs override SparkMax defaults
        merged = {**defaults, **kwargs}

        # Store each callback as self._cb_{name} (None if not provided)
        for cb_name in _VALID_CALLBACKS:
            setattr(self, f'_cb_{cb_name}', merged.get(cb_name))

        # Publish callback status to NT
        self._publish_callback_status()

        # Attempt to load persisted calibration from NT
        self._load_from_nt()

    # ---- Public properties ----

    @property
    def is_busy(self) -> bool:
        """True when homing or calibrating (blocks motor commands)."""
        return self._is_homing or self._is_calibrating

    @property
    def is_homing(self) -> bool:
        """Whether a homing routine is active."""
        return self._is_homing

    @property
    def is_calibrating(self) -> bool:
        """Whether a calibration routine is active."""
        return self._is_calibrating

    @property
    def is_calibrated(self) -> bool:
        """Whether the full mechanical range has been discovered."""
        return self._is_calibrated

    @property
    def is_zeroed(self) -> bool:
        """Whether the encoder has been aligned to a reference point."""
        return self._hard_limit_min is not None

    @property
    def min_limit(self):
        """Hard limit min, or None if uncalibrated."""
        return self._hard_limit_min

    @property
    def max_limit(self):
        """Hard limit max, or None if uncalibrated."""
        return self._hard_limit_max

    @property
    def min_soft_limit(self) -> float:
        """Current minimum soft limit."""
        return self._min_soft_limit

    @property
    def max_soft_limit(self) -> float:
        """Current maximum soft limit."""
        return self._max_soft_limit

    @property
    def soft_limit_margin(self) -> float:
        """Current safety margin as a fraction of the full range."""
        return self._soft_limit_margin

    # ---- Public methods ----

    def get_callbacks(self) -> dict:
        """
        Return a dict of all callback names and their current values.

        Each key is a callback name from _VALID_CALLBACKS. The value is
        the callable if set, or None if not set. Useful for inspecting
        which callbacks are configured::

            cbs = cal.get_callbacks()
            for name, func in cbs.items():
                print(f"{name}: {'set' if func else 'not set'}")

        Returns:
            dict mapping callback name -> callable or None
        """
        return {
            name: getattr(self, f'_cb_{name}', None)
            for name in sorted(_VALID_CALLBACKS)
        }

    def set_callbacks(self, **kwargs) -> None:
        """
        Set, override, or clear one or more callbacks by name.

        Pass a callable to set a callback, or None to clear it::

            # Set a callback
            cal.set_callbacks(get_velocity=encoder.getVelocity)

            # Clear callbacks that don't apply to this mechanism
            cal.set_callbacks(
                get_forward_limit_switch=None,
                get_reverse_limit_switch=None)

        Args:
            **kwargs: callback name/value pairs (see _VALID_CALLBACKS).
                Pass None to clear a callback.
        """
        for key, value in kwargs.items():
            if key not in _VALID_CALLBACKS:
                raise ValueError(f"Unknown callback: {key}")
            setattr(self, f'_cb_{key}', value)
        self._publish_callback_status()

    def homing_init(
        self,
        max_current: float,
        max_power_pct: float,
        max_homing_time: float,
        homing_forward: bool,
        min_velocity: float = None,
        home_position: float = 0.0
    ) -> None:
        """
        Initialize the sensorless or sensor homing routine.

        Saves current motor settings (if save_config callback is set),
        applies homing-specific configuration, and begins driving toward
        the specified hard stop.

        Args:
            max_current: current limit in amps during homing
            max_power_pct: motor duty cycle during homing (0.0-1.0)
            max_homing_time: maximum time in seconds before timeout
            homing_forward: True to home toward forward limit, False for reverse
            min_velocity: stall detection threshold in user units/second.
                Defaults to 5% of soft limit range over 2 seconds.
            home_position: encoder value to set when the hard stop is
                found (default 0.0)
        """
        # Validate callbacks before starting
        self._validate_homing(homing_forward)

        if min_velocity is None:
            full_range = self._max_soft_limit - self._min_soft_limit
            min_velocity = full_range * 0.05 / 2.0

        # Save current motor settings for restoration (if callback exists)
        if self._cb_save_config is not None:
            self._saved_config = self._cb_save_config()
        else:
            self._saved_config = None

        # Apply homing current limit (if callback exists)
        if self._cb_set_current_limit is not None:
            self._cb_set_current_limit(max_current)

        # Disable soft limit in homing direction (if callback exists)
        if self._cb_disable_soft_limits is not None:
            if homing_forward:
                self._cb_disable_soft_limits(True, False)
            else:
                self._cb_disable_soft_limits(False, True)

        # Store homing parameters
        self._homing_forward = homing_forward
        self._max_power_pct = max_power_pct
        self._min_velocity = min_velocity
        self._max_homing_time = max_homing_time
        self._home_position = home_position

        # Set homing state
        self._is_homing = True
        self._stall_detected = False

        # Start timeout timer
        self._homing_timer = wpilib.Timer()
        self._homing_timer.start()

        # Stall detection timer
        self._stall_timer = wpilib.Timer()

        # Alerts
        self._homing_status_alert = wpilib.Alert(
            f"{self._name}: homing started",
            wpilib.Alert.AlertType.kInfo
        )
        self._homing_status_alert.set(True)
        self._homing_error_alert = wpilib.Alert(
            f"{self._name}: homing failed",
            wpilib.Alert.AlertType.kError
        )
        self._homing_error_alert.set(False)

    def calibration_init(
        self,
        max_current: float,
        max_power_pct: float,
        max_homing_time: float,
        min_velocity: float = None,
        known_range: float = None
    ) -> None:
        """
        Start a calibration routine that discovers the mechanical range.

        Phase 1: Home negative to find the reverse hard limit (set as zero).
        Phase 2: Home positive to find the forward hard limit (measured).

        If known_range is provided, only phase 1 runs and the forward hard
        limit is computed as known_range from the zero point.

        Args:
            max_current: current limit in amps during calibration
            max_power_pct: motor duty cycle (0.0-1.0)
            max_homing_time: maximum time per phase before timeout
            min_velocity: stall detection threshold in user units/second
            known_range: if provided, skip phase 2 and use this as the
                full mechanical range from the zero point
        """
        # Validate callbacks before starting
        self._validate_calibration()

        # Save motor settings for restoration after calibration
        if self._cb_save_config is not None:
            self._cal_saved_config = self._cb_save_config()
        else:
            self._cal_saved_config = None

        # Disable both soft limits for free travel
        if self._cb_disable_soft_limits is not None:
            self._cb_disable_soft_limits(True, True)

        # Store calibration parameters for phase transitions
        self._cal_max_current = max_current
        self._cal_max_power_pct = max_power_pct
        self._cal_max_homing_time = max_homing_time
        self._cal_min_velocity = min_velocity
        self._cal_known_range = known_range

        self._is_calibrating = True
        self._calibration_phase = 1

        # Start phase 1: home negative
        self.homing_init(
            max_current, max_power_pct, max_homing_time,
            homing_forward=False, min_velocity=min_velocity
        )

        self._cal_status_alert = wpilib.Alert(
            f"{self._name}: calibration phase 1 - homing negative",
            wpilib.Alert.AlertType.kInfo
        )
        self._cal_status_alert.set(True)

    def periodic(self) -> None:
        """
        Run the active homing or calibration state machine.

        Call this every cycle when is_busy is True.
        """
        if self._is_calibrating:
            self._calibration_periodic()
        elif self._is_homing:
            self._homing_periodic()

    def abort(self) -> None:
        """Abort any active homing or calibration routine."""
        if self._is_calibrating:
            self._calibration_end(abort=True)
        elif self._is_homing:
            self._homing_end(abort=True)

    def set_soft_limit_margin(self, margin_pct: float) -> None:
        """
        Set the soft limit safety margin and apply to the motor controller.

        Args:
            margin_pct: safety margin as a fraction (e.g. 0.05 for 5%)
        """
        if not self._is_calibrated:
            return
        self._soft_limit_margin = margin_pct
        full_range = self._hard_limit_max - self._hard_limit_min
        margin = full_range * margin_pct
        self._min_soft_limit = self._hard_limit_min + margin
        self._max_soft_limit = self._hard_limit_max - margin

        # Apply to hardware only if callback exists
        if self._cb_set_soft_limits is not None:
            self._cb_set_soft_limits(
                self._min_soft_limit, self._max_soft_limit)

    def update_telemetry(self, prefix: str) -> None:
        """
        Publish calibration data to SmartDashboard.

        Args:
            prefix: SmartDashboard key prefix (e.g. "Turret/")
        """
        sd = wpilib.SmartDashboard
        sd.putBoolean(prefix + "isCalibrated", self._is_calibrated)
        sd.putBoolean(prefix + "isCalibrating", self._is_calibrating)
        sd.putBoolean(prefix + "isHoming", self._is_homing)
        sd.putNumber(
            prefix + "hardLimitMin",
            self._hard_limit_min if self._hard_limit_min is not None
            else 0.0
        )
        sd.putNumber(
            prefix + "hardLimitMax",
            self._hard_limit_max if self._hard_limit_max is not None
            else 0.0
        )
        sd.putNumber(prefix + "positionOffset", self._position_offset)
        sd.putNumber(prefix + "softLimitMargin", self._soft_limit_margin)

    # ---- Validation ----

    def _validate_homing(self, homing_forward: bool):
        """Validate callbacks needed for homing in the given direction."""
        missing = [n for n in sorted(_CORE_REQUIRED)
                   if getattr(self, f'_cb_{n}', None) is None]
        if missing:
            raise ValueError(
                f"Required callbacks not set: {', '.join(missing)}"
            )

        has_velocity = self._cb_get_velocity is not None
        if homing_forward:
            has_limit = self._cb_get_forward_limit_switch is not None
        else:
            has_limit = self._cb_get_reverse_limit_switch is not None

        if not has_velocity and not has_limit:
            direction = "forward" if homing_forward else "reverse"
            raise ValueError(
                f"No detection method for {direction} homing: "
                f"provide get_velocity and/or "
                f"get_{direction}_limit_switch"
            )

    def _validate_calibration(self):
        """Validate callbacks needed for full calibration."""
        if self._cb_get_position is None:
            raise ValueError(
                "get_position callback required for calibration"
            )
        # Need detection in both directions
        self._validate_homing(homing_forward=False)   # phase 1
        self._validate_homing(homing_forward=True)    # phase 2

    # ---- Internal methods ----

    def _publish_callback_status(self) -> None:
        """Write True/False for each callback to NT via ntproperty."""
        for cb_name in _VALID_CALLBACKS:
            is_set = getattr(self, f'_cb_{cb_name}', None) is not None
            setattr(self, f'_nt_cb_{cb_name}', is_set)

    def _homing_periodic(self) -> bool:
        """
        Periodic homing logic. Drives the motor, monitors for stall or
        limit switch, and handles timeout.

        Returns:
            True when homing is complete (success or failure), False if ongoing
        """
        if not self._is_homing:
            return True

        # Check timeout first
        if self._homing_timer.hasElapsed(self._max_homing_time):
            self._homing_error_alert.setText(
                f"{self._name}: homing failed - timeout"
            )
            self._homing_end(abort=True)
            return True

        # Check hard limit switch in homing direction (if callback exists)
        limit_hit = False
        if (self._homing_forward
                and self._cb_get_forward_limit_switch is not None):
            limit_hit = self._cb_get_forward_limit_switch()
        elif (not self._homing_forward
              and self._cb_get_reverse_limit_switch is not None):
            limit_hit = self._cb_get_reverse_limit_switch()

        # Drive motor in homing direction
        if self._homing_forward:
            self._cb_set_motor_output(self._max_power_pct)
        else:
            self._cb_set_motor_output(-self._max_power_pct)

        # Check for limit switch hit
        if limit_hit:
            home_position = self._home_position
            self._cb_set_position(home_position)
            if self._cb_on_limit_detected is not None:
                direction = (
                    "forward" if self._homing_forward else "reverse"
                )
                self._cb_on_limit_detected(home_position, direction)
            self._homing_status_alert.setText(
                f"{self._name}: homing complete"
            )
            self._homing_end(abort=False)
            return True

        # Stall detection only if velocity callback provided
        if self._cb_get_velocity is not None:
            velocity = abs(self._cb_get_velocity())

            if velocity < self._min_velocity:
                if not self._stall_detected:
                    self._stall_detected = True
                    self._stall_timer.restart()
                elif self._stall_timer.hasElapsed(0.1):
                    home_position = self._home_position
                    self._cb_set_position(home_position)
                    if self._cb_on_limit_detected is not None:
                        direction = (
                            "forward" if self._homing_forward
                            else "reverse"
                        )
                        self._cb_on_limit_detected(
                            home_position, direction)
                    self._homing_status_alert.setText(
                        f"{self._name}: homing complete"
                    )
                    self._homing_end(abort=False)
                    return True
            else:
                self._stall_detected = False
                self._stall_timer.stop()
                self._stall_timer.reset()

        return False

    def _homing_end(self, abort: bool) -> None:
        """
        Clean up after homing. Stops motor, restores saved settings,
        updates alerts.

        Args:
            abort: True if homing was aborted or failed
        """
        self._cb_stop_motor()

        # Restore saved motor settings (if we saved them)
        if (self._saved_config is not None
                and self._cb_restore_config is not None):
            self._cb_restore_config(self._saved_config)

        # Clear homing state
        self._is_homing = False
        self._homing_succeeded = not abort

        # Stop timers
        self._homing_timer.stop()
        self._stall_timer.stop()

        # Update alerts
        if abort:
            self._homing_error_alert.setText(
                f"{self._name}: homing aborted"
            )
            self._homing_error_alert.set(True)
            self._homing_status_alert.set(False)
        else:
            self._homing_error_alert.set(False)
            # After successful homing, if calibration data exists, the
            # encoder is now aligned so soft limits can be applied to
            # hardware
            if (not self._is_calibrating
                    and self._is_calibrated
                    and self._cb_set_soft_limits is not None):
                self._cb_set_soft_limits(
                    self._min_soft_limit, self._max_soft_limit)

    def _calibration_periodic(self) -> None:
        """Manage the two-phase calibration state machine."""
        if not self._is_calibrating:
            return

        if self._calibration_phase == 1:
            done = self._homing_periodic()
            if done:
                if self._homing_succeeded:
                    # Phase 1 complete - set encoder to 0
                    self._cb_set_position(0.0)
                    self._hard_limit_min = 0.0

                    if self._cal_known_range is not None:
                        self._hard_limit_max = self._cal_known_range
                        self._calibration_end(abort=False)
                    else:
                        self._cal_status_alert.setText(
                            f"{self._name}: calibration phase 2"
                            " - homing positive"
                        )
                        self._calibration_phase = 2
                        self.homing_init(
                            self._cal_max_current,
                            self._cal_max_power_pct,
                            self._cal_max_homing_time,
                            homing_forward=True,
                            min_velocity=self._cal_min_velocity
                        )
                else:
                    # Homing failed (timeout) - abort calibration
                    self._calibration_end(abort=True)

        elif self._calibration_phase == 2:
            measured_position = self._cb_get_position()
            done = self._homing_periodic()
            if done:
                if self._homing_succeeded:
                    self._hard_limit_max = measured_position
                    self._calibration_end(abort=False)
                else:
                    self._calibration_end(abort=True)

    def _calibration_end(self, abort: bool) -> None:
        """
        Clean up after calibration. Restores motor settings and on
        success computes and applies soft limits.

        Args:
            abort: True if calibration failed
        """
        self._cb_stop_motor()
        self._is_calibrating = False
        self._calibration_phase = 0
        self._is_homing = False

        if not abort and self._hard_limit_max is not None:
            self._is_calibrated = True
            self._cal_status_alert.setText(
                f"{self._name}: calibration complete"
            )
            self.set_soft_limit_margin(self._soft_limit_margin)
            self._save_to_nt()
        else:
            # Restore original config on abort
            if (self._cal_saved_config is not None
                    and self._cb_restore_config is not None):
                self._cb_restore_config(self._cal_saved_config)
            self._cal_status_alert.setText(
                f"{self._name}: calibration aborted"
            )

    def _save_to_nt(self) -> None:
        """Persist calibration data to NetworkTables via ntproperty."""
        if self._hard_limit_min is not None:
            self._nt_hard_limit_min = self._hard_limit_min
        if self._hard_limit_max is not None:
            self._nt_hard_limit_max = self._hard_limit_max
        self._nt_soft_limit_margin = self._soft_limit_margin

    def _load_from_nt(self) -> None:
        """Load persisted calibration data from ntproperty NT entries."""
        nt_min = self._nt_hard_limit_min
        nt_max = self._nt_hard_limit_max
        if not math.isnan(nt_min) and not math.isnan(nt_max):
            self._hard_limit_min = nt_min
            self._hard_limit_max = nt_max
            self._soft_limit_margin = self._nt_soft_limit_margin
            self._is_calibrated = True
            # Compute soft limits in memory only — don't push to hardware
            # because encoder position is unknown until homing completes
            full_range = self._hard_limit_max - self._hard_limit_min
            margin = full_range * self._soft_limit_margin
            self._min_soft_limit = self._hard_limit_min + margin
            self._max_soft_limit = self._hard_limit_max - margin
