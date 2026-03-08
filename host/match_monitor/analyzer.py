"""Parse .wpilog files and extract match statistics."""

import logging
import mmap
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .ds_log_reader import DsLogData

from wpiutil.log import DataLogReader

logger = logging.getLogger("match_monitor")

# Patterns to match entry names (case-insensitive)
VOLTAGE_PATTERNS = [
    re.compile(r'battery\s*voltage', re.IGNORECASE),
    re.compile(r'voltage', re.IGNORECASE),
]
BROWNOUT_PATTERNS = [
    re.compile(r'brownout', re.IGNORECASE),
    re.compile(r'browned?\s*out', re.IGNORECASE),
]
DS_CONNECTED_PATTERNS = [
    re.compile(r'DS:ds', re.IGNORECASE),
    re.compile(r'ds\s*attached', re.IGNORECASE),
    re.compile(r'ds\s*connected', re.IGNORECASE),
]
MODE_PATTERNS = {
    'enabled': re.compile(r'DS:enabled', re.IGNORECASE),
    'autonomous': re.compile(r'DS:autonomous', re.IGNORECASE),
    'test': re.compile(r'DS:test', re.IGNORECASE),
}
CONFIG_HASH_PATTERNS = [
    re.compile(r'controller.*hash', re.IGNORECASE),
    re.compile(r'config.*hash', re.IGNORECASE),
]
SYSTEM_TIME_PATTERNS = [
    re.compile(r'^systemTime$'),
    re.compile(r'system.*time', re.IGNORECASE),
]


@dataclass
class MatchStats:
    """Data class holding extracted match statistics."""
    brownout_count: int = 0
    brownout_timestamps_sec: List[float] = field(default_factory=list)
    disconnect_count: int = 0
    disconnect_timestamps_sec: List[float] = field(default_factory=list)
    start_voltage: Optional[float] = None
    end_voltage: Optional[float] = None
    avg_voltage: Optional[float] = None
    min_voltage: Optional[float] = None
    max_voltage: Optional[float] = None
    voltage_samples: int = 0
    match_duration_seconds: Optional[float] = None
    controller_config_hash: Optional[str] = None
    mode_transitions: List[dict] = field(default_factory=list)
    entry_names: List[str] = field(default_factory=list)
    # Wall clock time of the first wpilog record (derived from systemTime entry)
    wpilog_wall_start: Optional[datetime] = field(default=None, compare=False)
    # DS log data attached after collection (not part of wpilog analysis)
    ds_log: Optional['DsLogData'] = field(default=None, compare=False)

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        d = asdict(self)
        # Remove non-serializable fields handled separately
        d.pop('wpilog_wall_start', None)
        d.pop('ds_log', None)
        # Group voltage fields
        d['voltage'] = {
            'start': d.pop('start_voltage'),
            'end': d.pop('end_voltage'),
            'average': d.pop('avg_voltage'),
            'min': d.pop('min_voltage'),
            'max': d.pop('max_voltage'),
            'samples': d.pop('voltage_samples'),
        }
        if self.wpilog_wall_start:
            d['wpilog_wall_start'] = self.wpilog_wall_start.isoformat()
        if self.ds_log is not None:
            d['ds_log'] = self.ds_log.to_dict()
        return d


def _match_any(name: str, patterns: list) -> bool:
    return any(p.search(name) for p in patterns)


class WpilogAnalyzer:
    """Parses .wpilog files to extract match statistics."""

    def analyze(self, wpilog_path: Path) -> MatchStats:
        """Analyze a single .wpilog file and return match statistics."""
        stats = MatchStats()

        with open(wpilog_path, 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            reader = DataLogReader(mm)

            if not reader.isValid():
                logger.warning(f"Invalid wpilog file: {wpilog_path.name}")
                return stats

            # First pass: discover entry names and their IDs
            entries: Dict[int, dict] = {}  # entry_id -> {name, type}
            voltage_ids = set()
            brownout_ids = set()
            ds_connected_ids = set()
            mode_ids: Dict[str, set] = {k: set() for k in MODE_PATTERNS}
            config_hash_ids = set()
            system_time_ids = set()

            for record in reader:
                if record.isStart():
                    data = record.getStartData()
                    entries[data.entry] = {
                        'name': data.name, 'type': data.type
                    }
                    stats.entry_names.append(data.name)

                    if _match_any(data.name, VOLTAGE_PATTERNS):
                        voltage_ids.add(data.entry)
                    if _match_any(data.name, BROWNOUT_PATTERNS):
                        brownout_ids.add(data.entry)
                    if _match_any(data.name, DS_CONNECTED_PATTERNS):
                        ds_connected_ids.add(data.entry)
                    for mode_name, pattern in MODE_PATTERNS.items():
                        if pattern.search(data.name):
                            mode_ids[mode_name].add(data.entry)
                    if _match_any(data.name, CONFIG_HASH_PATTERNS):
                        config_hash_ids.add(data.entry)
                    if _match_any(data.name, SYSTEM_TIME_PATTERNS):
                        system_time_ids.add(data.entry)

            # Log discovered entries
            logger.info(f"Analyzing {wpilog_path.name}: "
                        f"{len(entries)} entries, "
                        f"voltage={len(voltage_ids)}, "
                        f"brownout={len(brownout_ids)}, "
                        f"ds_connected={len(ds_connected_ids)}")

            # Second pass: extract data
            voltage_sum = 0.0
            voltage_count = 0
            first_timestamp = None
            last_timestamp = None
            prev_brownout = False
            prev_ds_connected = True
            mode_state: Dict[str, bool] = {}

            mm.seek(0)
            reader2 = DataLogReader(mm)

            for record in reader2:
                if record.isControl():
                    continue

                entry_info = entries.get(record.getEntry())
                if entry_info is None:
                    continue

                ts_sec = record.getTimestamp() / 1_000_000.0
                if first_timestamp is None:
                    first_timestamp = ts_sec
                last_timestamp = ts_sec

                try:
                    # Voltage
                    if record.getEntry() in voltage_ids:
                        v = self._get_numeric(record, entry_info['type'])
                        if v is not None:
                            if stats.start_voltage is None:
                                stats.start_voltage = v
                            stats.end_voltage = v
                            voltage_sum += v
                            voltage_count += 1
                            if stats.min_voltage is None or v < stats.min_voltage:
                                stats.min_voltage = v
                            if stats.max_voltage is None or v > stats.max_voltage:
                                stats.max_voltage = v

                    # Brownout
                    if record.getEntry() in brownout_ids:
                        val = record.getBoolean()
                        if val and not prev_brownout:
                            stats.brownout_count += 1
                            stats.brownout_timestamps_sec.append(
                                round(ts_sec - (first_timestamp or 0), 3)
                            )
                        prev_brownout = val

                    # DS Connected
                    if record.getEntry() in ds_connected_ids:
                        val = record.getBoolean()
                        if not val and prev_ds_connected:
                            stats.disconnect_count += 1
                            stats.disconnect_timestamps_sec.append(
                                round(ts_sec - (first_timestamp or 0), 3)
                            )
                        prev_ds_connected = val

                    # Mode transitions
                    for mode_name, ids in mode_ids.items():
                        if record.getEntry() in ids:
                            val = record.getBoolean()
                            prev = mode_state.get(mode_name)
                            if prev is None or val != prev:
                                mode_state[mode_name] = val
                                if val:
                                    stats.mode_transitions.append({
                                        'time_sec': round(
                                            ts_sec - (first_timestamp or 0), 3
                                        ),
                                        'mode': mode_name,
                                    })

                    # Controller config hash
                    if record.getEntry() in config_hash_ids:
                        stats.controller_config_hash = record.getString()

                    # System time — wall clock offset for DS log correlation
                    if record.getEntry() in system_time_ids and stats.wpilog_wall_start is None:
                        try:
                            entry_type = entries[record.getEntry()]['type']
                            if entry_type == 'int64':
                                # Microseconds since Unix epoch
                                wall_us = record.getInteger()
                                wall_sec = wall_us / 1_000_000.0
                                stats.wpilog_wall_start = datetime.fromtimestamp(
                                    wall_sec, tz=timezone.utc)
                            elif entry_type == 'string':
                                raw = record.getString()
                                for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
                                    try:
                                        stats.wpilog_wall_start = datetime.strptime(
                                            raw[:19], fmt).replace(tzinfo=timezone.utc)
                                        break
                                    except ValueError:
                                        pass  # try next format
                        except Exception as e:
                            logger.debug("Could not parse system time entry: %s", e)

                except Exception as e:
                    logger.debug("Skipping malformed record: %s", e)

            # Finalize
            if voltage_count > 0:
                stats.avg_voltage = round(voltage_sum / voltage_count, 3)
                stats.voltage_samples = voltage_count
                if stats.start_voltage is not None:
                    stats.start_voltage = round(stats.start_voltage, 3)
                if stats.end_voltage is not None:
                    stats.end_voltage = round(stats.end_voltage, 3)
                if stats.min_voltage is not None:
                    stats.min_voltage = round(stats.min_voltage, 3)
                if stats.max_voltage is not None:
                    stats.max_voltage = round(stats.max_voltage, 3)

            if first_timestamp is not None and last_timestamp is not None:
                stats.match_duration_seconds = round(
                    last_timestamp - first_timestamp, 3
                )

            mm.close()

        return stats

    def analyze_directory(self, match_dir: Path) -> MatchStats:
        """Analyze all .wpilog files in a directory and merge results."""
        wpilog_files = sorted(match_dir.glob('*.wpilog'))
        if not wpilog_files:
            logger.info(f"No .wpilog files found in {match_dir}")
            return MatchStats()

        all_stats = []
        for f in wpilog_files:
            try:
                s = self.analyze(f)
                all_stats.append(s)
            except Exception:
                logger.exception(f"Failed to analyze {f.name}")

        if not all_stats:
            return MatchStats()
        if len(all_stats) == 1:
            return all_stats[0]
        return self._merge(all_stats)

    def _merge(self, stats_list: List[MatchStats]) -> MatchStats:
        """Merge stats from multiple .wpilog files."""
        merged = MatchStats()
        total_voltage_sum = 0.0
        total_voltage_count = 0

        for s in stats_list:
            merged.brownout_count += s.brownout_count
            merged.brownout_timestamps_sec.extend(s.brownout_timestamps_sec)
            merged.disconnect_count += s.disconnect_count
            merged.disconnect_timestamps_sec.extend(s.disconnect_timestamps_sec)
            merged.mode_transitions.extend(s.mode_transitions)
            merged.entry_names.extend(s.entry_names)

            if s.start_voltage is not None and merged.start_voltage is None:
                merged.start_voltage = s.start_voltage
            if s.end_voltage is not None:
                merged.end_voltage = s.end_voltage
            if s.min_voltage is not None:
                if merged.min_voltage is None or s.min_voltage < merged.min_voltage:
                    merged.min_voltage = s.min_voltage
            if s.max_voltage is not None:
                if merged.max_voltage is None or s.max_voltage > merged.max_voltage:
                    merged.max_voltage = s.max_voltage
            if s.voltage_samples > 0 and s.avg_voltage is not None:
                total_voltage_sum += s.avg_voltage * s.voltage_samples
                total_voltage_count += s.voltage_samples
            if s.match_duration_seconds is not None:
                if (merged.match_duration_seconds is None
                        or s.match_duration_seconds > merged.match_duration_seconds):
                    merged.match_duration_seconds = s.match_duration_seconds
            if s.controller_config_hash is not None:
                merged.controller_config_hash = s.controller_config_hash

        if total_voltage_count > 0:
            merged.avg_voltage = round(total_voltage_sum / total_voltage_count, 3)
            merged.voltage_samples = total_voltage_count

        merged.mode_transitions.sort(key=lambda t: t['time_sec'])
        merged.entry_names = sorted(set(merged.entry_names))
        return merged

    @staticmethod
    def _get_numeric(record, type_name: str):
        if type_name == 'double':
            return record.getDouble()
        elif type_name == 'float':
            return record.getFloat()
        elif type_name == 'int64':
            return float(record.getInteger())
        return None
