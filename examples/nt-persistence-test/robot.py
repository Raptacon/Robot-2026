"""
NT Persistence Test Example

Minimal TimedCommandRobot that demonstrates three approaches for persisting
calibration data across reboots via NetworkTables:

1. wpilib.Preferences - high-level API, auto-persisted to
   .wpilib/wpilib_preferences.json
2. Raw ntcore persistent topics - lower-level, persisted via
   networktables.json
3. ntcore.util.ntproperty - class-level descriptors that read/write NT
   entries like normal Python attributes. With persistent=True, values
   survive reboots automatically.

All three publish to SmartDashboard for side-by-side comparison.
Xbox controller buttons trigger write/read/clear operations.
"""

import wpilib
import ntcore
from ntcore.util import ntproperty
from commands2 import TimedCommandRobot, cmd
from commands2.button import CommandXboxController


# Keys used for preferences and raw NT approaches
CAL_KEYS = ["hard_limit_min", "hard_limit_max", "soft_limit_margin"]
CAL_DEFAULTS = {"hard_limit_min": 0.0, "hard_limit_max": 180.0,
                "soft_limit_margin": 0.05}
NT_PREFIX = "Turret/calibration/"


class MyRobot(TimedCommandRobot):
    # --- Approach 3: ntproperty descriptors ---
    # These behave like normal Python attributes but are backed by NT.
    # persistent=True means values survive reboots.
    # writeDefault=False avoids overwriting persisted values on startup.
    nt_hard_limit_min = ntproperty(
        "/Turret/calibration/ntprop/hard_limit_min", 0.0,
        writeDefault=False, persistent=True,
        doc="Hard limit min via ntproperty"
    )
    nt_hard_limit_max = ntproperty(
        "/Turret/calibration/ntprop/hard_limit_max", 180.0,
        writeDefault=False, persistent=True,
        doc="Hard limit max via ntproperty"
    )
    nt_soft_limit_margin = ntproperty(
        "/Turret/calibration/ntprop/soft_limit_margin", 0.05,
        writeDefault=False, persistent=True,
        doc="Soft limit margin via ntproperty"
    )

    def __init__(self):
        super().__init__(period=0.02)

    def robotInit(self):
        self.sd = wpilib.SmartDashboard

        # --- Approach 1: wpilib.Preferences ---
        self.prefs = wpilib.Preferences
        for key in CAL_KEYS:
            pref_key = NT_PREFIX + key
            if not self.prefs.containsKey(pref_key):
                self.prefs.setDouble(pref_key, CAL_DEFAULTS[key])

        # --- Approach 2: Raw ntcore persistent topics ---
        inst = ntcore.NetworkTableInstance.getDefault()
        self.nt_table = inst.getTable(NT_PREFIX + "raw")
        self.nt_entries = {}

        for key in CAL_KEYS:
            topic = self.nt_table.getDoubleTopic(key)
            entry = topic.getEntry(CAL_DEFAULTS[key])
            print(
                f"NT Test: created topic '{topic.getName()}'"
                f" with default {CAL_DEFAULTS[key]}"
            )
            self.nt_entries[key] = entry
            # Set value before properties to avoid "unpublished topic" warning
            if not entry.exists():
                entry.set(CAL_DEFAULTS[key])
            topic.setRetained(True)
            topic.setPersistent(True)

        # Approach 3 (ntproperty) is already set up as class attributes.
        # Just log the initial values.
        print(
            f"NT Test: ntproperty initial values:"
            f" min={self.nt_hard_limit_min},"
            f" max={self.nt_hard_limit_max},"
            f" margin={self.nt_soft_limit_margin}"
        )

        self.sd.putString(
            "NT Test/instructions",
            "A=Write B=Read X=Clear  (3 approaches: prefs, raw, ntproperty)"
        )

    def teleopInit(self):
        self.controller = CommandXboxController(0)

        # A button: Write test values
        self.controller.a().onTrue(self._write_cmd())
        # B button: Read and display values
        self.controller.b().onTrue(self._read_cmd())
        # X button: Clear / reset to defaults
        self.controller.x().onTrue(self._clear_cmd())

    def _write_cmd(self):
        """Write test calibration values to all three stores."""
        def write():
            test_vals = {"hard_limit_min": -5.0, "hard_limit_max": 185.0,
                         "soft_limit_margin": 0.08}
            for key, val in test_vals.items():
                # Approach 1: Preferences
                self.prefs.setDouble(NT_PREFIX + key, val)
                # Approach 2: Raw NT
                self.nt_entries[key].set(val)

            # Approach 3: ntproperty (just assign like normal attributes)
            self.nt_hard_limit_min = test_vals["hard_limit_min"]
            self.nt_hard_limit_max = test_vals["hard_limit_max"]
            self.nt_soft_limit_margin = test_vals["soft_limit_margin"]

            self.sd.putString("NT Test/status", "Wrote test values")
            print("NT Test: wrote test values to all 3 approaches")

        return cmd.runOnce(write)

    def _read_cmd(self):
        """Read values from all three stores and publish to dashboard."""
        def read():
            for key in CAL_KEYS:
                # Approach 1: Preferences
                pref_val = self.prefs.getDouble(
                    NT_PREFIX + key, CAL_DEFAULTS[key])
                self.sd.putNumber(f"NT Test/prefs/{key}", pref_val)

                # Approach 2: Raw NT
                raw_val = self.nt_entries[key].get(CAL_DEFAULTS[key])
                self.sd.putNumber(f"NT Test/raw/{key}", raw_val)

            # Approach 3: ntproperty (just read like normal attributes)
            self.sd.putNumber(
                "NT Test/ntprop/hard_limit_min", self.nt_hard_limit_min)
            self.sd.putNumber(
                "NT Test/ntprop/hard_limit_max", self.nt_hard_limit_max)
            self.sd.putNumber(
                "NT Test/ntprop/soft_limit_margin",
                self.nt_soft_limit_margin)

            self.sd.putString("NT Test/status", "Read values")
            print(
                f"NT Test: read values"
                f" | ntprop: min={self.nt_hard_limit_min},"
                f" max={self.nt_hard_limit_max},"
                f" margin={self.nt_soft_limit_margin}"
            )

        return cmd.runOnce(read)

    def _clear_cmd(self):
        """Reset all three stores to defaults."""
        def clear():
            for key in CAL_KEYS:
                # Approach 1
                self.prefs.setDouble(NT_PREFIX + key, CAL_DEFAULTS[key])
                # Approach 2
                self.nt_entries[key].set(CAL_DEFAULTS[key])

            # Approach 3: ntproperty
            self.nt_hard_limit_min = CAL_DEFAULTS["hard_limit_min"]
            self.nt_hard_limit_max = CAL_DEFAULTS["hard_limit_max"]
            self.nt_soft_limit_margin = CAL_DEFAULTS["soft_limit_margin"]

            self.sd.putString("NT Test/status", "Cleared to defaults")
            print("NT Test: cleared all 3 approaches to defaults")

        return cmd.runOnce(clear)

    def teleopPeriodic(self):
        pass
