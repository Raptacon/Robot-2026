"""
Locate, copy, and parse FRC Driver Station log files.

DS Log files are stored in C:\\Users\\Public\\Documents\\FRC\\Log Files\\ with names:
  2024_01_15_15_23_45 FRC.dslog     — 50Hz binary data
  2024_01_15_15_23_45 FRC.dsevents  — text event log

dsevents format (tab-separated fields per line):
  <seconds_from_log_start>\\t<message>\\t[detail]

dslog binary format (v3, 50Hz):
  Header (16 bytes): version(4) + start_time_ms(8) + reserved(4)
  Each record (21 bytes):
    uint8  packet_loss_pct
    uint8  trip_time_ms
    uint16 battery_voltage  (big-endian, volts * 256.0)
    uint8  robot_voltage    (volts * 10.2, approx)
    uint8  status_flags     (bit0=estop, bit1=disabled, bit2=auto, bit3=enabled,
                             bit4=robot_code, bit5=ds_link, bit6=fms_link)
    uint8  can_utilization_pct
    uint8  signal_quality_pct
    uint8  robot_cpu_pct
    uint8  ds_cpu_pct
    uint8  ram_pct
    uint16 bandwidth_kbps   (big-endian)
    uint8  pdp_channel_0_current (x 8 ... varies by record type)
    -- remaining bytes vary --
"""

import logging
import re
import shutil
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("match_monitor")

# Default DS log directory (Windows Driver Station)
DS_LOG_DIR = Path(r"C:\Users\Public\Documents\FRC\Log Files")

# Filename timestamp pattern: "2024_01_15_15_23_45 FRC"
_DS_FNAME_RE = re.compile(
    r"(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})\s+FRC\.(dslog|dsevents)$",
    re.IGNORECASE,
)

# How far before/after the match window to look for a DS log file (seconds)
_MATCH_WINDOW_SLOP = 300  # 5 minutes


@dataclass
class DsEvent:
    """A single entry from a .dsevents file."""
    offset_sec: float     # Seconds from log start
    message: str
    detail: str = ""


@dataclass
class DsRecord:
    """One 50Hz record from a .dslog file."""
    offset_sec: float
    packet_loss_pct: int
    trip_time_ms: int
    battery_voltage: float
    signal_quality_pct: int
    robot_cpu_pct: int
    ds_cpu_pct: int
    ram_pct: int
    can_utilization_pct: int
    bandwidth_kbps: int
    enabled: bool
    autonomous: bool
    fms_link: bool
    ds_link: bool


@dataclass
class DsLogData:
    """Parsed content from DS log files for one match."""
    log_start_wall: Optional[datetime] = None   # Wall clock of log file start
    events: List[DsEvent] = field(default_factory=list)
    records: List[DsRecord] = field(default_factory=list)
    copied_files: List[str] = field(default_factory=list)

    # Derived summary (filled by summarize())
    avg_packet_loss_pct: Optional[float] = None
    max_trip_time_ms: Optional[int] = None
    avg_trip_time_ms: Optional[float] = None
    min_battery_v: Optional[float] = None
    avg_battery_v: Optional[float] = None
    peak_ds_cpu_pct: Optional[int] = None
    peak_robot_cpu_pct: Optional[int] = None
    peak_ram_pct: Optional[int] = None
    peak_bandwidth_kbps: Optional[int] = None

    def summarize(self) -> None:
        """Compute derived summary fields from raw records."""
        if not self.records:
            return
        self.avg_packet_loss_pct = round(
            sum(r.packet_loss_pct for r in self.records) / len(self.records), 1)
        self.max_trip_time_ms = max(r.trip_time_ms for r in self.records)
        self.avg_trip_time_ms = round(
            sum(r.trip_time_ms for r in self.records) / len(self.records), 1)
        voltages = [r.battery_voltage for r in self.records if r.battery_voltage > 0]
        if voltages:
            self.min_battery_v = round(min(voltages), 3)
            self.avg_battery_v = round(sum(voltages) / len(voltages), 3)
        self.peak_ds_cpu_pct = max(r.ds_cpu_pct for r in self.records)
        self.peak_robot_cpu_pct = max(r.robot_cpu_pct for r in self.records)
        self.peak_ram_pct = max(r.ram_pct for r in self.records)
        self.peak_bandwidth_kbps = max(r.bandwidth_kbps for r in self.records)

    def to_dict(self) -> dict:
        d = {
            'log_start_wall': self.log_start_wall.isoformat() if self.log_start_wall else None,
            'copied_files': self.copied_files,
            'event_count': len(self.events),
            'record_count': len(self.records),
            'events': [
                {'offset_sec': e.offset_sec, 'message': e.message, 'detail': e.detail}
                for e in self.events
            ],
        }
        if self.records:
            d['summary'] = {
                'avg_packet_loss_pct': self.avg_packet_loss_pct,
                'avg_trip_time_ms': self.avg_trip_time_ms,
                'max_trip_time_ms': self.max_trip_time_ms,
                'min_battery_v': self.min_battery_v,
                'avg_battery_v': self.avg_battery_v,
                'peak_robot_cpu_pct': self.peak_robot_cpu_pct,
                'peak_ds_cpu_pct': self.peak_ds_cpu_pct,
                'peak_ram_pct': self.peak_ram_pct,
                'peak_bandwidth_kbps': self.peak_bandwidth_kbps,
            }
        return d


def _parse_filename_time(path: Path) -> Optional[datetime]:
    """Extract datetime from a DS log filename, or None if unrecognized."""
    m = _DS_FNAME_RE.match(path.name)
    if not m:
        return None
    year, month, day, hour, minute, second = (int(m.group(i)) for i in range(1, 7))
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def find_match_logs(match_time: datetime,
                    ds_log_dir: Path = DS_LOG_DIR) -> List[Path]:
    """
    Find DS log files whose filename timestamp is within MATCH_WINDOW_SLOP
    seconds of match_time.  Returns a list of .dslog / .dsevents paths.
    """
    if not ds_log_dir.is_dir():
        return []

    window = timedelta(seconds=_MATCH_WINDOW_SLOP)
    results = []
    for path in ds_log_dir.iterdir():
        if path.suffix.lower() not in ('.dslog', '.dsevents'):
            continue
        file_time = _parse_filename_time(path)
        if file_time is None:
            continue
        if abs(file_time - match_time) <= window:
            results.append(path)

    results.sort()
    return results


def copy_ds_logs(paths: List[Path], dest_dir: Path) -> List[str]:
    """Copy DS log files into dest_dir. Returns list of copied filenames."""
    copied = []
    for src in paths:
        dest = dest_dir / src.name
        if dest.exists():
            copied.append(src.name)
            continue
        try:
            shutil.copy2(src, dest)
            copied.append(src.name)
            logger.info(f"Copied DS log: {src.name}")
        except OSError:
            logger.warning(f"Could not copy DS log: {src.name}")
    return copied


def parse_dsevents(path: Path) -> tuple[Optional[datetime], List[DsEvent]]:
    """
    Parse a .dsevents file.  Returns (log_start_wall, [DsEvent, ...]).

    The file contains tab-separated lines:
        <float_seconds>\\t<message>[\\t<detail>]
    The log start wall time is inferred from the filename.
    """
    log_start = _parse_filename_time(path)
    events = []
    try:
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            try:
                offset = float(parts[0])
            except ValueError:
                continue
            message = parts[1].strip()
            detail = parts[2].strip() if len(parts) > 2 else ""
            events.append(DsEvent(offset_sec=round(offset, 3),
                                  message=message, detail=detail))
    except OSError:
        logger.warning(f"Could not read DS events file: {path.name}")
    return log_start, events


# dslog record: packet_loss(B) trip_time(B) battery_v(H) robot_v(B)
# status(B) can(B) signal(B) robot_cpu(B) ds_cpu(B) ram(B) bandwidth(H)
# = 13 bytes; remaining bytes in record vary (PDP dumps etc.)
_RECORD_FMT = struct.Struct('>BBHBBBBBBBH')       # 12 bytes
_RECORD_SIZE = 21  # total record size including PDP/trailing bytes


def parse_dslog(path: Path) -> tuple[Optional[datetime], List[DsRecord]]:
    """
    Parse a .dslog binary file.  Returns (log_start_wall, [DsRecord, ...]).

    Note: The binary format is community-documented and may vary slightly
    between DS versions.  Fields beyond the core 12 bytes are skipped.
    """
    log_start = _parse_filename_time(path)
    records = []
    try:
        data = path.read_bytes()
    except OSError:
        logger.warning(f"Could not read DS log file: {path.name}")
        return log_start, records

    if len(data) < 16:
        return log_start, records

    # Version check
    version = struct.unpack_from('>I', data, 0)[0]
    if version != 3:
        logger.warning(f"Unsupported dslog version {version} in {path.name}")
        return log_start, records

    offset = 16  # skip header
    record_index = 0
    while offset + _RECORD_FMT.size <= len(data):
        try:
            (packet_loss, trip_time, batt_raw, robot_v_raw,
             status, can_pct, signal_pct, robot_cpu, ds_cpu,
             ram_pct, bw_kbps) = _RECORD_FMT.unpack_from(data, offset)

            battery_v = batt_raw / 256.0
            enabled = bool(status & 0x08)
            autonomous = bool(status & 0x04)
            ds_link = bool(status & 0x20)
            fms_link = bool(status & 0x40)

            records.append(DsRecord(
                offset_sec=round(record_index / 50.0, 3),
                packet_loss_pct=min(packet_loss, 100),
                trip_time_ms=trip_time,
                battery_voltage=round(battery_v, 3),
                signal_quality_pct=signal_pct,
                robot_cpu_pct=robot_cpu,
                ds_cpu_pct=ds_cpu,
                ram_pct=ram_pct,
                can_utilization_pct=can_pct,
                bandwidth_kbps=bw_kbps,
                enabled=enabled,
                autonomous=autonomous,
                fms_link=fms_link,
                ds_link=ds_link,
            ))
        except struct.error:
            break

        offset += _RECORD_SIZE
        record_index += 1

    logger.info(f"Parsed {len(records)} records from {path.name}")
    return log_start, records


def collect_for_match(match_time: datetime, dest_dir: Path,
                      ds_log_dir: Path = DS_LOG_DIR) -> DsLogData:
    """
    Find DS logs matching match_time, copy them to dest_dir, parse them,
    and return a populated DsLogData.
    """
    result = DsLogData()

    paths = find_match_logs(match_time, ds_log_dir)
    if not paths:
        logger.info("No matching DS log files found")
        return result

    result.copied_files = copy_ds_logs(paths, dest_dir)

    for path in paths:
        suffix = path.suffix.lower()
        local = dest_dir / path.name   # work from the copy

        if suffix == '.dsevents':
            wall_time, events = parse_dsevents(local)
            if wall_time and result.log_start_wall is None:
                result.log_start_wall = wall_time
            result.events.extend(events)

        elif suffix == '.dslog':
            wall_time, records = parse_dslog(local)
            if wall_time and result.log_start_wall is None:
                result.log_start_wall = wall_time
            result.records.extend(records)

    result.summarize()
    return result
