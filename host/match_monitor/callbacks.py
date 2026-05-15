"""Callback registry for post-match processing."""

import base64
import json
import logging
import webbrowser
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from .analyzer import MatchStats

if TYPE_CHECKING:
    from .match_data_client import MatchResult, EventStats

logger = logging.getLogger("match_monitor")


class MatchCompleteCallback(ABC):
    """Base class for end-of-match processing callbacks."""

    @abstractmethod
    def on_match_complete(self, match_dir: Path, metadata: dict,
                          stats: MatchStats,
                          match_result: Optional['MatchResult'] = None,
                          event_stats: Optional['EventStats'] = None) -> None:
        """Called after match log analysis completes.

        Args:
            match_dir: Directory containing the match log files.
            metadata: Dict with event_name, match_type, match_number.
            stats: Extracted match statistics.
            match_result: Official match result from TBA/FRC Events API, or None.
            event_stats: OPR/rankings data for our team, or None.
        """


class CallbackRegistry:
    """Manages and runs end-of-match callbacks."""

    def __init__(self) -> None:
        self._callbacks: List[MatchCompleteCallback] = []

    def register(self, callback: MatchCompleteCallback) -> None:
        self._callbacks.append(callback)
        logger.info(f"Registered callback: {type(callback).__name__}")

    def unregister(self, callback: MatchCompleteCallback) -> None:
        try:
            self._callbacks.remove(callback)
            logger.info(f"Unregistered callback: {type(callback).__name__}")
        except ValueError:
            pass

    def run_all(self, match_dir: Path, metadata: dict,
                stats: MatchStats,
                match_result: Optional['MatchResult'] = None,
                event_stats: Optional['EventStats'] = None) -> None:
        for cb in self._callbacks:
            try:
                cb.on_match_complete(match_dir, metadata, stats,
                                     match_result, event_stats)
            except Exception:
                logger.exception(
                    f"Callback {type(cb).__name__} failed"
                )


class JsonSummaryCallback(MatchCompleteCallback):
    """Saves match_summary.json in the match directory."""

    def on_match_complete(self, match_dir: Path, metadata: dict,
                          stats: MatchStats,
                          match_result: Optional['MatchResult'] = None,
                          event_stats: Optional['EventStats'] = None) -> None:
        summary = {
            'event_name': metadata.get('event_name', ''),
            'match_type': metadata.get('match_type', ''),
            'match_number': metadata.get('match_number', ''),
            'analyzed_at': datetime.now().isoformat(),
        }
        summary.update(stats.to_dict())

        if match_result is not None:
            summary['official_match'] = match_result.to_dict()
        if event_stats is not None:
            summary['event_stats'] = event_stats.to_dict()

        out_path = match_dir / 'match_summary.json'
        out_path.write_text(json.dumps(summary, indent=2) + '\n')
        logger.info(f"Saved {out_path}")


class HtmlPreviewCallback(MatchCompleteCallback):
    """Generates a local HTML preview page and opens it in the browser."""

    def on_match_complete(self, match_dir: Path, metadata: dict,
                          stats: MatchStats,
                          match_result: Optional['MatchResult'] = None,
                          event_stats: Optional['EventStats'] = None) -> None:
        # Generate voltage chart
        chart_b64 = ''
        if stats.voltage_timeseries:
            try:
                from .chart_generator import voltage_chart
                chart_png = voltage_chart(
                    stats.voltage_timeseries,
                    brownout_times=stats.brownout_timestamps_sec,
                    mode_transitions=stats.mode_transitions,
                    match_duration=stats.match_duration_seconds,
                )
                if chart_png:
                    chart_b64 = base64.b64encode(chart_png).decode('ascii')
            except Exception:
                logger.exception("Chart generation failed for HTML preview")

        match_type = metadata.get('match_type', 'Match') or 'Match'
        match_number = metadata.get('match_number', '?') or '?'
        event_name = metadata.get('event_name', '') or ''
        title = f"{match_type.capitalize()} {match_number}"
        if event_name:
            title = f"[{event_name.upper()}] {title}"

        # Build stats rows
        rows = []
        if stats.avg_voltage is not None:
            rows.append(('Battery Voltage',
                         f"Start {stats.start_voltage}V &middot; "
                         f"Avg {stats.avg_voltage}V &middot; "
                         f"Min {stats.min_voltage}V &middot; "
                         f"Max {stats.max_voltage}V"))
        rows.append(('Brownouts', f"{stats.brownout_count}"
                      + (f" @ {', '.join(f'{t}s' for t in stats.brownout_timestamps_sec[:5])}"
                         if stats.brownout_count else '')))
        rows.append(('Disconnects', f"{stats.disconnect_count}"
                      + (f" @ {', '.join(f'{t}s' for t in stats.disconnect_timestamps_sec[:5])}"
                         if stats.disconnect_count else '')))
        if stats.match_duration_seconds is not None:
            rows.append(('Log Duration', f"{stats.match_duration_seconds:.1f}s"))
        if stats.rail_voltages:
            for rail, rv in stats.rail_voltages.items():
                rows.append((f"Rail {rail}",
                             f"Avg {rv['avg']}V &middot; "
                             f"Min {rv['min']}V &middot; "
                             f"Max {rv['max']}V"))
        if stats.ds_log and stats.ds_log.avg_packet_loss_pct is not None:
            rows.append(('Packet Loss', f"{stats.ds_log.avg_packet_loss_pct}%"))
        if stats.ds_log and stats.ds_log.avg_trip_time_ms is not None:
            rows.append(('Latency',
                         f"avg {stats.ds_log.avg_trip_time_ms}ms / "
                         f"max {stats.ds_log.max_trip_time_ms}ms"))

        stats_html = '\n'.join(
            f'<tr><td><b>{name}</b></td><td>{val}</td></tr>' for name, val in rows
        )
        chart_html = (f'<img src="data:image/png;base64,{chart_b64}" '
                      f'style="max-width:100%">' if chart_b64 else
                      '<p><i>No chart data</i></p>')

        html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>{title} - Match Preview</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 900px; margin: 40px auto; padding: 0 20px;
         background: #1a1a2e; color: #e0e0e0; }}
  h1 {{ color: #3498db; }}
  table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #333; }}
  tr:hover {{ background: #252545; }}
  .chart {{ margin: 20px 0; text-align: center; }}
  .timestamp {{ color: #666; font-size: 0.85em; }}
</style>
</head><body>
<h1>{title}</h1>
<p class="timestamp">Analyzed {datetime.now():%Y-%m-%d %H:%M:%S}</p>
<div class="chart">{chart_html}</div>
<h2>Match Statistics</h2>
<table>{stats_html}</table>
</body></html>"""

        out_path = match_dir / 'match_preview.html'
        out_path.write_text(html, encoding='utf-8')
        logger.info(f"Saved HTML preview: {out_path}")
        print(f"  Opening preview: {out_path}")
        webbrowser.open(out_path.as_uri())
