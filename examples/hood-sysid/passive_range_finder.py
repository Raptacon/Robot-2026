"""
Passive range finder command for discovering mechanism range of motion.

Sets coast mode so a mechanism can be moved by hand. Tracks min/max
encoder positions, detects hard limit switches, and applies the
discovered range as soft limits when stopped.
"""

import ntcore
import rev
import wpilib
from commands2 import Command, Subsystem


class PassiveRangeFinderCommand(Command):
    """
    Command that lets you passively move a motor through its range of
    motion to discover min/max positions.

    On start: saves config, sets coast mode so mechanism moves freely.
    While running: tracks min/max encoder positions, checks limit switches.
    On stop: applies discovered range as soft limits, restores idle mode.

    Bind to a button with toggleOnTrue for start/stop behavior.
    """

    def __init__(
        self,
        motor: rev.SparkMax,
        name: str,
        subsystem: Subsystem,
        zero_on_end: bool = False,
        full_range: float = None,
    ) -> None:
        super().__init__()
        self.motor = motor
        self.encoder = motor.getEncoder()
        self._name = name
        self._subsystem = subsystem
        self._zero_on_end = zero_on_end
        self._full_range = full_range
        self.addRequirements(subsystem)

        # State
        self._min_raw = 0.0
        self._max_raw = 0.0
        self._start_time = 0.0
        self._original_conversion_factor = 1.0
        self._original_idle_mode = rev.SparkBaseConfig.IdleMode.kBrake
        self._hit_forward_limit = False
        self._hit_reverse_limit = False
        self._forward_limit_position = 0.0
        self._reverse_limit_position = 0.0

        # NT table
        self._table = ntcore.NetworkTableInstance.getDefault().getTable(
            f"PassiveRangeFinder/{name}")

        # Alerts
        self._fwd_alert = wpilib.Alert(
            f"PassiveRangeFinder/{name}: Forward hard limit hit",
            wpilib.Alert.AlertType.kWarning)
        self._rev_alert = wpilib.Alert(
            f"PassiveRangeFinder/{name}: Reverse hard limit hit",
            wpilib.Alert.AlertType.kWarning)
        self._result_alert = wpilib.Alert(
            f"PassiveRangeFinder/{name}: Results pending",
            wpilib.Alert.AlertType.kInfo)

    def initialize(self) -> None:
        """Save config, set coast mode, start tracking."""
        ca = self.motor.configAccessor

        # Save original config
        self._original_idle_mode = ca.getIdleMode()
        self._original_conversion_factor = (
            ca.encoder.getPositionConversionFactor())

        # Set conversion factor to 1.0 for raw encoder units, coast mode
        # position: 1.0 = raw rotations
        # velocity: 1/60 = rotations/sec (from RPM)
        cfg = rev.SparkMaxConfig()
        cfg.setIdleMode(rev.SparkBaseConfig.IdleMode.kCoast)
        (
            cfg.encoder
            .positionConversionFactor(1.0)
            .velocityConversionFactor(1.0 / 60.0)
        )
        self.motor.configure(
            cfg,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        # Zero encoder and reset tracking
        self.encoder.setPosition(0)
        pos = 0.0
        self._min_raw = pos
        self._max_raw = pos
        self._hit_forward_limit = False
        self._hit_reverse_limit = False
        self._forward_limit_position = 0.0
        self._reverse_limit_position = 0.0
        self._start_time = wpilib.Timer.getFPGATimestamp()

        # Clear alerts
        self._fwd_alert.set(False)
        self._rev_alert.set(False)
        self._result_alert.set(False)

        # Initialize NT entries
        self._publish_nt(pos)

        print(f"[PassiveRangeFinder/{self._name}] Started. "
              f"Move mechanism through its range, then press button again.")

    def execute(self) -> None:
        """Track min/max position and check limit switches."""
        pos = self.encoder.getPosition()

        # Update min/max
        if pos < self._min_raw:
            self._min_raw = pos
        if pos > self._max_raw:
            self._max_raw = pos

        # Check forward limit switch
        if (not self._hit_forward_limit
                and self.motor.getForwardLimitSwitch().get()):
            self._hit_forward_limit = True
            self._forward_limit_position = pos
            self._fwd_alert.setText(
                f"PassiveRangeFinder/{self._name}: Forward hard limit "
                f"at raw={pos:.4f} "
                f"normalized={pos * self._original_conversion_factor:.2f}")
            self._fwd_alert.set(True)

        # Check reverse limit switch
        if (not self._hit_reverse_limit
                and self.motor.getReverseLimitSwitch().get()):
            self._hit_reverse_limit = True
            self._reverse_limit_position = pos
            self._rev_alert.setText(
                f"PassiveRangeFinder/{self._name}: Reverse hard limit "
                f"at raw={pos:.4f} "
                f"normalized={pos * self._original_conversion_factor:.2f}")
            self._rev_alert.set(True)

        self._publish_nt(pos)

    def end(self, interrupted: bool) -> None:
        """Apply discovered range as soft limits and restore idle mode."""
        self.motor.stopMotor()

        cfg = rev.SparkMaxConfig()
        cfg.setIdleMode(self._original_idle_mode)

        # Determine best limits in raw encoder units
        fwd_raw = (self._forward_limit_position
                   if self._hit_forward_limit else self._max_raw)
        rev_raw = (self._reverse_limit_position
                   if self._hit_reverse_limit else self._min_raw)

        # Offset relative to current position when zeroing
        current_raw = self.encoder.getPosition()
        if self._zero_on_end:
            fwd_raw -= current_raw
            rev_raw -= current_raw

        range_raw = self._max_raw - self._min_raw

        # Compute new conversion factor from measured range.
        # full_range given (e.g. 20 degrees): encoder reads 0..20
        # full_range not given: encoder reads 0..1
        if range_raw > 0:
            if self._full_range is not None:
                cf = self._full_range / range_raw
            else:
                cf = 1.0 / range_raw
        else:
            cf = self._original_conversion_factor

        # position: cf units/rotation (deg or normalized)
        # velocity: cf/60 = units/sec (from RPM)
        (
            cfg.encoder
            .positionConversionFactor(cf)
            .velocityConversionFactor(cf / 60.0)
        )

        # Apply soft limits in the new units
        fwd_scaled = fwd_raw * cf
        rev_scaled = rev_raw * cf

        (
            cfg.softLimit
            .forwardSoftLimit(fwd_scaled)
            .forwardSoftLimitEnabled(True)
            .reverseSoftLimit(rev_scaled)
            .reverseSoftLimitEnabled(True)
        )

        elapsed = wpilib.Timer.getFPGATimestamp() - self._start_time
        unit = ("deg" if self._full_range is not None
                else "normalized")

        summary = (
            f"[PassiveRangeFinder/{self._name}] Complete.\n"
            f"  Raw rotations: min={self._min_raw:.4f}  "
            f"max={self._max_raw:.4f}  range={range_raw:.4f}\n"
            f"  Conversion factor: {cf:.4f} {unit}/rotation\n"
            f"  Soft limits: [{rev_scaled:.2f}, {fwd_scaled:.2f}] {unit}"
        )
        if self._zero_on_end:
            summary += (
                f"\n  Zeroed at raw={current_raw:.4f}")
        summary += (
            f"\n  Forward limit hit: {self._hit_forward_limit}\n"
            f"  Reverse limit hit: {self._hit_reverse_limit}\n"
            f"  Elapsed: {elapsed:.1f}s"
        )
        print(summary)

        limits_str = (
            'fwd+rev' if self._hit_forward_limit
            and self._hit_reverse_limit
            else 'fwd' if self._hit_forward_limit
            else 'rev' if self._hit_reverse_limit
            else 'none')
        self._result_alert.setText(
            f"PassiveRangeFinder/{self._name}: "
            f"range=[{rev_scaled:.2f}, {fwd_scaled:.2f}] {unit} "
            f"hardLimits={limits_str}")
        self._result_alert.set(True)

        self.motor.configure(
            cfg,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        # Zero the encoder after config is applied so soft limits
        # are relative to the new zero position.
        if self._zero_on_end:
            self.encoder.setPosition(0)

        # Tell the subsystem to hold at current position so its
        # periodic PID doesn't drive back to the old target.
        if hasattr(self._subsystem, 'disable') and callable(
                self._subsystem.disable):
            self._subsystem.disable()

        # Final NT update
        self._table.putBoolean("active", False)

    def isFinished(self) -> bool:
        return False

    def _publish_nt(self, position: float) -> None:
        """Publish all telemetry to NetworkTables."""
        t = self._table
        elapsed = wpilib.Timer.getFPGATimestamp() - self._start_time
        range_raw = self._max_raw - self._min_raw

        # Live normalized: 0..1 based on range seen so far
        if range_raw > 0:
            norm = (position - self._min_raw) / range_raw
        else:
            norm = 0.0

        t.putBoolean("active", True)
        t.putNumber("currentRaw", position)
        t.putNumber("currentNormalized", norm)
        t.putNumber("minRaw", self._min_raw)
        t.putNumber("maxRaw", self._max_raw)
        t.putNumber("rangeRaw", range_raw)
        t.putNumber("elapsedTime", elapsed)
        t.putBoolean("passedForwardHardLimit", self._hit_forward_limit)
        t.putBoolean("passedReverseHardLimit", self._hit_reverse_limit)
        t.putNumber("forwardLimitRaw", self._forward_limit_position)
        t.putNumber("reverseLimitRaw", self._reverse_limit_position)
