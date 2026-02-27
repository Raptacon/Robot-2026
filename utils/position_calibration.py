# Native imports
import math

# Third-party imports
import rev
import wpilib
from ntcore.util import ntproperty


# Cache of dynamically-created subclasses keyed by mechanism name.
# Each subclass has ntproperty descriptors with NT paths unique to
# that mechanism, so multiple PositionCalibration instances with
# different names get independent persistent storage.
_calibration_classes = {}


class PositionCalibration:
    """
    Reusable calibration and homing controller for positional mechanisms.

    Extracts sensorless homing and two-phase calibration logic from
    mechanism-specific subsystems into a standalone class. Works with any
    SparkMax + relative encoder setup (turret, elevator, arm, etc.).

    Calibration discovers mechanical hard limits by driving into stops,
    then computes soft limits with a configurable safety margin. Persists
    discovered limits to NetworkTables via ntproperty so values survive
    reboots.

    Typical usage:
        self.calibration = PositionCalibration(
            name="Turret", motor=self.motor, encoder=self.encoder,
            default_min_soft_limit=-90, default_max_soft_limit=90)

        # In periodic():
        if self.calibration.is_busy:
            self.calibration.periodic()
    """

    def __init__(
        self,
        name: str,
        motor: rev.SparkMax,
        encoder: rev.RelativeEncoder,
        default_min_soft_limit: float,
        default_max_soft_limit: float,
    ) -> None:
        """
        Create a new PositionCalibration controller.

        Args:
            name: mechanism name used for NT paths and alerts (e.g. "Turret")
            motor: the SparkMax motor controller
            encoder: the relative encoder from the motor
            default_min_soft_limit: default reverse soft limit in user units
            default_max_soft_limit: default forward soft limit in user units
        """
        # Assign this instance to a cached subclass with ntproperty
        # descriptors keyed to this mechanism's name. ntproperty is a
        # class-level descriptor, so each mechanism name needs its own
        # class to avoid key collisions. The cache ensures the
        # ntproperty is created only once per name so defaults don't
        # overwrite previously persisted values.
        if name not in _calibration_classes:
            prefix = f"/{name}/calibration"
            _calibration_classes[name] = type(
                f"PositionCalibration_{name}",
                (PositionCalibration,),
                {
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
            )
        self.__class__ = _calibration_classes[name]

        self._name = name
        self._motor = motor
        self._encoder = encoder

        # Default soft limits (used before calibration)
        self._default_min_soft_limit = default_min_soft_limit
        self._default_max_soft_limit = default_max_soft_limit

        # Current soft limits
        self._min_soft_limit = default_min_soft_limit
        self._max_soft_limit = default_max_soft_limit

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

    def homing_init(
        self,
        max_current: float,
        max_power_pct: float,
        max_homing_time: float,
        homing_forward: bool,
        min_velocity: float = None
    ) -> None:
        """
        Initialize the sensorless homing routine.

        Saves current motor settings, applies homing-specific configuration,
        and begins driving toward the specified hard stop.

        Args:
            max_current: current limit in amps during homing
            max_power_pct: motor duty cycle during homing (0.0-1.0)
            max_homing_time: maximum time in seconds before timeout
            homing_forward: True to home toward forward limit, False for reverse
            min_velocity: stall detection threshold in user units/second.
                Defaults to 5% of soft limit range over 2 seconds.
        """
        if min_velocity is None:
            full_range = self._max_soft_limit - self._min_soft_limit
            min_velocity = full_range * 0.05 / 2.0

        # Save current motor settings for restoration
        ca = self._motor.configAccessor
        self._saved_current_limit = ca.getSmartCurrentLimit()
        self._saved_current_free_limit = ca.getSmartCurrentFreeLimit()
        self._saved_current_rpm_limit = ca.getSmartCurrentRPMLimit()
        self._saved_fwd_soft_limit_enabled = (
            ca.softLimit.getForwardSoftLimitEnabled()
        )
        self._saved_rev_soft_limit_enabled = (
            ca.softLimit.getReverseSoftLimitEnabled()
        )

        # Apply homing configuration
        homing_config = rev.SparkMaxConfig()
        homing_config.smartCurrentLimit(int(max_current))
        if homing_forward:
            homing_config.softLimit.forwardSoftLimitEnabled(False)
        else:
            homing_config.softLimit.reverseSoftLimitEnabled(False)

        self._motor.configure(
            homing_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        # Store homing parameters
        self._homing_forward = homing_forward
        self._max_power_pct = max_power_pct
        self._min_velocity = min_velocity
        self._max_homing_time = max_homing_time

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
        # Save motor settings for restoration after calibration
        ca = self._motor.configAccessor
        self._cal_saved_current_limit = ca.getSmartCurrentLimit()
        self._cal_saved_current_free_limit = ca.getSmartCurrentFreeLimit()
        self._cal_saved_current_rpm_limit = ca.getSmartCurrentRPMLimit()
        self._cal_saved_fwd_soft_limit_enabled = (
            ca.softLimit.getForwardSoftLimitEnabled()
        )
        self._cal_saved_rev_soft_limit_enabled = (
            ca.softLimit.getReverseSoftLimitEnabled()
        )
        self._cal_saved_fwd_soft_limit = ca.softLimit.getForwardSoftLimit()
        self._cal_saved_rev_soft_limit = ca.softLimit.getReverseSoftLimit()

        # Disable both soft limits for free travel
        disable_config = rev.SparkMaxConfig()
        (
            disable_config.softLimit
            .forwardSoftLimitEnabled(False)
            .reverseSoftLimitEnabled(False)
        )
        self._motor.configure(
            disable_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

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

        limit_config = rev.SparkMaxConfig()
        (
            limit_config.softLimit
            .forwardSoftLimit(self._max_soft_limit)
            .forwardSoftLimitEnabled(True)
            .reverseSoftLimit(self._min_soft_limit)
            .reverseSoftLimitEnabled(True)
        )
        self._motor.configure(
            limit_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

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

    # ---- Internal methods ----

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

        # Check hard limit switch in homing direction
        if self._homing_forward:
            limit_hit = self._motor.getForwardLimitSwitch().get()
        else:
            limit_hit = self._motor.getReverseLimitSwitch().get()

        # Drive motor in homing direction
        if self._homing_forward:
            self._motor.set(self._max_power_pct)
        else:
            self._motor.set(-self._max_power_pct)

        # Check for stall or limit switch
        velocity = abs(self._encoder.getVelocity())

        if limit_hit:
            home_position = (
                self._max_soft_limit if self._homing_forward
                else self._min_soft_limit
            )
            self._encoder.setPosition(home_position)
            self._homing_status_alert.setText(
                f"{self._name}: homing complete"
            )
            self._homing_end(abort=False)
            return True

        if velocity < self._min_velocity:
            if not self._stall_detected:
                self._stall_detected = True
                self._stall_timer.restart()
            elif self._stall_timer.hasElapsed(0.1):
                home_position = (
                    self._max_soft_limit if self._homing_forward
                    else self._min_soft_limit
                )
                self._encoder.setPosition(home_position)
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
        self._motor.stopMotor()

        # Restore saved motor settings
        restore_config = rev.SparkMaxConfig()
        restore_config.smartCurrentLimit(
            int(self._saved_current_limit),
            int(self._saved_current_free_limit),
            int(self._saved_current_rpm_limit)
        )
        (
            restore_config.softLimit
            .forwardSoftLimitEnabled(self._saved_fwd_soft_limit_enabled)
            .reverseSoftLimitEnabled(self._saved_rev_soft_limit_enabled)
        )
        self._motor.configure(
            restore_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        # Clear homing state
        self._is_homing = False

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

    def _calibration_periodic(self) -> None:
        """Manage the two-phase calibration state machine."""
        if not self._is_calibrating:
            return

        if self._calibration_phase == 1:
            done = self._homing_periodic()
            if done:
                if not self._is_homing:
                    # Phase 1 complete - set encoder to 0
                    self._encoder.setPosition(0.0)
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
            measured_position = self._encoder.getPosition()
            done = self._homing_periodic()
            if done:
                if not self._is_homing:
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
        self._motor.stopMotor()
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
            # Restore original soft limits on abort
            restore_config = rev.SparkMaxConfig()
            restore_config.smartCurrentLimit(
                int(self._cal_saved_current_limit),
                int(self._cal_saved_current_free_limit),
                int(self._cal_saved_current_rpm_limit)
            )
            (
                restore_config.softLimit
                .forwardSoftLimit(self._cal_saved_fwd_soft_limit)
                .forwardSoftLimitEnabled(
                    self._cal_saved_fwd_soft_limit_enabled)
                .reverseSoftLimit(self._cal_saved_rev_soft_limit)
                .reverseSoftLimitEnabled(
                    self._cal_saved_rev_soft_limit_enabled)
            )
            self._motor.configure(
                restore_config,
                rev.ResetMode.kNoResetSafeParameters,
                rev.PersistMode.kNoPersistParameters
            )
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
            self.set_soft_limit_margin(self._soft_limit_margin)
