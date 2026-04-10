"""
Continuous loop-timing instrumentation.

Measures how much of the timed robot periodic budget the robot code consumes,
broken down by channel (e.g. userCode vs scheduler).  Stats are published
to SmartDashboard every cycle so they are always visible — not only on
overrun like the built-in CommandScheduler Watchdog.

Timing uses FPGA timestamps (microsecond resolution on real hardware).
In simulation the values reflect simulated time, not wall-clock.
"""

import math
import wpilib


class LoopTimingStats:
    """Running statistics accumulator (Welford's online algorithm).

    All public values are in **milliseconds**.  Input to :meth:`record`
    is in seconds (matching ``Timer.getFPGATimestamp()`` units).
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._count: int = 0
        self._min: float = float("inf")
        self._max: float = float("-inf")
        self._last: float = 0.0
        # Welford accumulators
        self._mean: float = 0.0
        self._m2: float = 0.0

    def record(self, duration_sec: float):
        """Record one sample.  *duration_sec* is converted to ms internally."""
        ms = duration_sec * 1000.0
        self._last = ms
        self._count += 1

        if ms < self._min:
            self._min = ms
        if ms > self._max:
            self._max = ms

        # Welford's online update
        delta = ms - self._mean
        self._mean += delta / self._count
        delta2 = ms - self._mean
        self._m2 += delta * delta2

    @property
    def count(self) -> int:
        return self._count

    @property
    def min_ms(self) -> float:
        return self._min if self._count > 0 else 0.0

    @property
    def max_ms(self) -> float:
        return self._max if self._count > 0 else 0.0

    @property
    def avg_ms(self) -> float:
        return self._mean if self._count > 0 else 0.0

    @property
    def stddev_ms(self) -> float:
        if self._count < 2:
            return 0.0
        return math.sqrt(self._m2 / (self._count - 1))

    @property
    def last_ms(self) -> float:
        return self._last


class LoopTimer:
    """Coordinator that manages named timing channels and publishes stats.

    Typical usage::

        timer = LoopTimer(budget_sec=0.020)
        timer.add_channel("userCode")
        timer.add_channel("scheduler")

        # each cycle:
        timer.start("userCode")
        ...
        timer.stop("userCode")
        timer.publish()
    """

    def __init__(self, budget_sec: float):
        self._budget_ms = budget_sec * 1000.0
        self._channels: dict[str, LoopTimingStats] = {}
        self._starts: dict[str, float] = {}
        self._alert_info = wpilib.Alert(
            "Frame Timing", wpilib.Alert.AlertType.kInfo
        )
        self._alert_warning = wpilib.Alert(
            "Frame Timing", wpilib.Alert.AlertType.kWarning
        )
        self._alert_error = wpilib.Alert(
            "Frame Timing", wpilib.Alert.AlertType.kError
        )

    def add_channel(self, name: str):
        self._channels[name] = LoopTimingStats()

    def start(self, name: str):
        self._starts[name] = wpilib.Timer.getFPGATimestamp()

    def stop(self, name: str):
        end = wpilib.Timer.getFPGATimestamp()
        begin = self._starts.pop(name, end)
        self._channels[name].record(end - begin)

    def reset_all(self):
        for stats in self._channels.values():
            stats.reset()
        self._starts.clear()

    def publish(self):
        total_ms = 0.0
        for name, stats in self._channels.items():
            prefix = f"FrameTiming/{name}"
            wpilib.SmartDashboard.putNumber(f"{prefix}/lastMs", stats.last_ms)
            wpilib.SmartDashboard.putNumber(f"{prefix}/minMs", stats.min_ms)
            wpilib.SmartDashboard.putNumber(f"{prefix}/maxMs", stats.max_ms)
            wpilib.SmartDashboard.putNumber(f"{prefix}/avgMs", stats.avg_ms)
            wpilib.SmartDashboard.putNumber(f"{prefix}/stddevMs", stats.stddev_ms)
            wpilib.SmartDashboard.putNumber(f"{prefix}/count", stats.count)
            if self._budget_ms > 0:
                wpilib.SmartDashboard.putNumber(
                    f"{prefix}/budgetPct",
                    (stats.last_ms / self._budget_ms) * 100.0,
                )
            total_ms += stats.last_ms

        wpilib.SmartDashboard.putNumber("FrameTiming/totalMs", total_ms)
        total_pct = 0.0
        if self._budget_ms > 0:
            total_pct = (total_ms / self._budget_ms) * 100.0
            wpilib.SmartDashboard.putNumber(
                "FrameTiming/totalBudgetPct", total_pct,
            )

        # Alert based on budget usage
        overrun = total_pct >= 100.0
        warning = total_pct >= 80.0 and not overrun
        info = not warning and not overrun

        self._alert_error.set(overrun)
        self._alert_warning.set(warning)
        self._alert_info.set(info)

        if overrun:
            self._alert_error.setText(
                f"Frame Timing: OVERRUN {total_pct:.0f}% ({total_ms:.1f}ms)"
            )
        elif warning:
            self._alert_warning.setText(
                f"Frame Timing: {total_pct:.0f}% - possible overrun"
            )
        else:
            self._alert_info.setText(
                f"Frame Timing: {total_pct:.0f}%"
            )
