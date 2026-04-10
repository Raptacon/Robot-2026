# Native imports
import csv
import math
import os
import time
from pathlib import Path
from typing import Callable

# Internal imports
from commands.default_swerve_drive_circular import circle_to_square

# Third-party imports
import commands2


class LogStickTransforms(commands2.Command):
    """Log raw joystick input alongside each transform's output to CSV.

    Captures both sticks on the drive controller every cycle and writes:
      - Raw X/Y (direct from HID, pre-shaping pipeline)
      - Shaped X/Y (post-pipeline: deadband, curve, scale, slew)
      - Circle-to-square X/Y (circular remapping applied to shaped values)

    Run this as a default command in test mode, move the sticks through
    their full range, then use the CSV to graph point clouds of each
    mapping. Output goes to logs/stick_transform_<timestamp>.csv.
    """

    def __init__(
        self,
        velocity_vector_x: Callable[[], float],
        velocity_vector_y: Callable[[], float],
        rotate: Callable[[], float],
    ) -> None:
        """
        Args:
            velocity_vector_x: ManagedAnalog for left stick X (translate)
            velocity_vector_y: ManagedAnalog for left stick Y (translate)
            rotate: ManagedAnalog for right stick X (rotate)
        """
        super().__init__()

        self.velocity_vector_x = velocity_vector_x
        self.velocity_vector_y = velocity_vector_y
        self.rotate = rotate

        # CSV setup — write to logs/ directory
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._csv_path = log_dir / f"stick_transform_{timestamp}.csv"
        self._csv_file = None
        self._csv_writer = None

    def initialize(self) -> None:
        # Line-buffered so data survives if the sim is killed without clean shutdown
        self._csv_file = open(self._csv_path, "w", newline="", buffering=1)
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            "timestamp_s",
            # Left stick (translate)
            "left_raw_x", "left_raw_y",
            "left_shaped_x", "left_shaped_y",
            "left_c2s_x", "left_c2s_y",
            # Right stick X (rotate) — single axis
            "right_raw_x",
            "right_shaped_x",
        ])
        self._csv_file.flush()
        self._start_time = time.monotonic()
        self._cycle_count = 0
        print(f"[LogStickTransforms] Logging to {self._csv_path}")

    def execute(self) -> None:
        t = time.monotonic() - self._start_time

        # Shaped values (post-pipeline)
        shaped_x = self.velocity_vector_x()
        shaped_y = self.velocity_vector_y()
        shaped_rot = self.rotate()

        # Raw HID values (pre-pipeline)
        raw_x = getattr(self.velocity_vector_x, 'getRaw', lambda: shaped_x)()
        raw_y = getattr(self.velocity_vector_y, 'getRaw', lambda: shaped_y)()
        raw_rot = getattr(self.rotate, 'getRaw', lambda: shaped_rot)()

        # Circle-to-square transform on shaped values
        c2s_x, c2s_y = circle_to_square(shaped_x, shaped_y)

        self._csv_writer.writerow([
            f"{t:.4f}",
            f"{raw_x:.6f}", f"{raw_y:.6f}",
            f"{shaped_x:.6f}", f"{shaped_y:.6f}",
            f"{c2s_x:.6f}", f"{c2s_y:.6f}",
            f"{raw_rot:.6f}",
            f"{shaped_rot:.6f}",
        ])
        # Flush every 50 cycles (~1s) so data isn't lost on unclean exit
        self._cycle_count += 1
        if self._cycle_count % 50 == 0:
            self._csv_file.flush()

    def end(self, interrupted: bool) -> None:
        if self._csv_file:
            self._csv_file.close()
            print(f"[LogStickTransforms] Saved {self._csv_path}")

    def isFinished(self) -> bool:
        return False
