"""Callback registry for post-match processing."""

import json
import logging
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
