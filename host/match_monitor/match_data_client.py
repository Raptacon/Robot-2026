"""
Fetch official match data from The Blue Alliance (TBA) and FRC Events API.

Configuration is read from a JSON file (default: match_monitor_config.json
next to the server log directory).  Create it with your API keys:

    {
        "tba_api_key": "YOUR_TBA_KEY",
        "frc_events_username": "YOUR_USERNAME",
        "frc_events_auth_key": "YOUR_AUTH_KEY",
        "team_number": 3200
    }

TBA keys: https://www.thebluealliance.com (Account > Read API Keys)
FRC Events keys: https://frc-events.firstinspires.org/services/api/register
"""

import base64
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("match_monitor")

_TBA_BASE = "https://www.thebluealliance.com/api/v3"
_FRC_BASE = "https://frc-api.firstinspires.org/v2.0"
_TIMEOUT = 10  # seconds


@dataclass
class AllianceResult:
    teams: list[str] = field(default_factory=list)   # e.g. ["frc3200", "frc1234", "frc5678"]
    score: Optional[int] = None
    won: bool = False


@dataclass
class MatchResult:
    """Official match result from TBA / FRC Events API."""
    match_key: str = ""           # e.g. "2026calas_qm12"
    event_key: str = ""           # e.g. "2026calas"
    match_number: int = 0
    tournament_level: str = ""    # "qm", "sf", "f"
    red: AllianceResult = field(default_factory=AllianceResult)
    blue: AllianceResult = field(default_factory=AllianceResult)
    score_breakdown: dict = field(default_factory=dict)
    our_alliance: str = ""        # "red" or "blue"
    our_score: Optional[int] = None
    opponent_score: Optional[int] = None
    result: str = ""              # "win", "loss", "tie", "unknown"
    video_url: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'match_key': self.match_key,
            'event_key': self.event_key,
            'match_number': self.match_number,
            'tournament_level': self.tournament_level,
            'red': {'teams': self.red.teams, 'score': self.red.score},
            'blue': {'teams': self.blue.teams, 'score': self.blue.score},
            'score_breakdown': self.score_breakdown,
            'our_alliance': self.our_alliance,
            'our_score': self.our_score,
            'opponent_score': self.opponent_score,
            'result': self.result,
            'video_url': self.video_url,
        }


@dataclass
class EventStats:
    """OPR/rankings data for the team at this event."""
    opr: Optional[float] = None
    dpr: Optional[float] = None
    ccwm: Optional[float] = None
    rank: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    ties: Optional[int] = None
    ranking_points: Optional[float] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if v is not None}


def _load_config(config_path: Path) -> dict:
    """Load API key config from JSON file.  Returns empty dict if missing."""
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except Exception:
            logger.warning(f"Failed to read match data config: {config_path}")
    return {}


def _tba_get(endpoint: str, api_key: str) -> Optional[dict | list]:
    """Make a GET request to the TBA API.  Returns parsed JSON or None."""
    url = f"{_TBA_BASE}/{endpoint.lstrip('/')}"
    req = urllib.request.Request(url, headers={
        'X-TBA-Auth-Key': api_key,
        'User-Agent': 'FRC3200-MatchMonitor/1.0',
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.warning(f"TBA API error {e.code} for {endpoint}")
    except urllib.error.URLError as e:
        # Connection failure (no internet, DNS, timeout) — expected offline
        logger.debug(f"TBA API unreachable ({e.reason})")
    except Exception as e:
        logger.debug(f"TBA API request failed for {endpoint}: {e}")
    return None


def _frc_get(endpoint: str, username: str, auth_key: str) -> Optional[dict | list]:
    """Make a GET request to the FRC Events API.  Returns parsed JSON or None."""
    url = f"{_FRC_BASE}/{endpoint.lstrip('/')}"
    token = base64.b64encode(f"{username}:{auth_key}".encode()).decode()
    req = urllib.request.Request(url, headers={
        'Authorization': f'Basic {token}',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.warning(f"FRC Events API error {e.code} for {endpoint}")
    except urllib.error.URLError as e:
        # Connection failure (no internet, DNS, timeout) — expected offline
        logger.debug(f"FRC Events API unreachable ({e.reason})")
    except Exception as e:
        logger.debug(f"FRC Events API request failed for {endpoint}: {e}")
    return None


def _alliance_result_from_tba(raw: dict) -> AllianceResult:
    return AllianceResult(
        teams=raw.get('team_keys', []),
        score=raw.get('score'),
    )


class MatchDataClient:
    """Fetches match data from TBA and FRC Events API for a given team/event."""

    def __init__(self, config_path: Path) -> None:
        cfg = _load_config(config_path)
        self._tba_key: str = cfg.get('tba_api_key', '')
        self._frc_user: str = cfg.get('frc_events_username', '')
        self._frc_auth: str = cfg.get('frc_events_auth_key', '')
        self._team_num: int = int(cfg.get('team_number', 3200))
        self._team_key = f"frc{self._team_num}"

    @property
    def configured(self) -> bool:
        return bool(self._tba_key or (self._frc_user and self._frc_auth))

    def fetch_match(self, event_key: str, match_number: int,
                    level: str = 'qm') -> Optional[MatchResult]:
        """
        Fetch a single match result.
        level: 'qm' (qualification), 'sf' (semifinal), 'f' (final)
        """
        match_key = f"{event_key}_{level}{match_number}"

        if self._tba_key:
            result = self._fetch_match_tba(match_key)
            if result:
                return result

        if self._frc_user and self._frc_auth:
            return self._fetch_match_frc(event_key, match_number, level)

        return None

    def _fetch_match_tba(self, match_key: str) -> Optional[MatchResult]:
        data = _tba_get(f"/match/{match_key}", self._tba_key)
        if not data or not isinstance(data, dict):
            return None

        alliances = data.get('alliances', {})
        red = _alliance_result_from_tba(alliances.get('red', {}))
        blue = _alliance_result_from_tba(alliances.get('blue', {}))

        # Determine winner
        winning_alliance = data.get('winning_alliance', '')
        if winning_alliance == 'red':
            red.won = True
        elif winning_alliance == 'blue':
            blue.won = True

        # Find our alliance
        our_alliance = ''
        if self._team_key in red.teams:
            our_alliance = 'red'
        elif self._team_key in blue.teams:
            our_alliance = 'blue'

        our_score = (red.score if our_alliance == 'red' else
                     blue.score if our_alliance == 'blue' else None)
        opp_score = (blue.score if our_alliance == 'red' else
                     red.score if our_alliance == 'blue' else None)

        result_str = 'unknown'
        if our_alliance:
            if winning_alliance == our_alliance:
                result_str = 'win'
            elif winning_alliance and winning_alliance != our_alliance:
                result_str = 'loss'
            elif winning_alliance == '':
                result_str = 'tie'

        # Video URL (first available)
        video_url = None
        for vid in data.get('videos', []):
            if vid.get('type') == 'youtube':
                video_url = f"https://www.youtube.com/watch?v={vid['key']}"
                break

        # Score breakdown (game-specific)
        breakdown = data.get('score_breakdown') or {}

        return MatchResult(
            match_key=data.get('key', ''),
            event_key=data.get('event_key', ''),
            match_number=data.get('match_number', 0),
            tournament_level=data.get('comp_level', ''),
            red=red,
            blue=blue,
            score_breakdown=breakdown,
            our_alliance=our_alliance,
            our_score=our_score,
            opponent_score=opp_score,
            result=result_str,
            video_url=video_url,
        )

    def _fetch_match_frc(self, event_key: str, match_number: int,
                          level: str) -> Optional[MatchResult]:
        year = event_key[:4]
        event_code = event_key[4:]
        level_map = {'qm': 'Qualification', 'sf': 'Playoff', 'f': 'Playoff'}
        tournament_level = level_map.get(level, 'Qualification')
        data = _frc_get(
            f"/{year}/matches/{event_code}?matchNumber={match_number}"
            f"&tournamentLevel={tournament_level}",
            self._frc_user, self._frc_auth,
        )
        if not data or not isinstance(data, dict):
            return None

        matches = data.get('Matches', [])
        if not matches:
            return None

        m = matches[0]
        red_teams = [f"frc{t['teamNumber']}" for t in m.get('teams', [])
                     if t.get('station', '').startswith('Red')]
        blue_teams = [f"frc{t['teamNumber']}" for t in m.get('teams', [])
                      if t.get('station', '').startswith('Blue')]
        red_score = m.get('scoreRedFinal')
        blue_score = m.get('scoreBlueFinal')

        our_alliance = ''
        if self._team_key in red_teams:
            our_alliance = 'red'
        elif self._team_key in blue_teams:
            our_alliance = 'blue'

        our_score = red_score if our_alliance == 'red' else blue_score if our_alliance == 'blue' else None
        opp_score = blue_score if our_alliance == 'red' else red_score if our_alliance == 'blue' else None

        result_str = 'unknown'
        if our_score is not None and opp_score is not None:
            if our_score > opp_score:
                result_str = 'win'
            elif our_score < opp_score:
                result_str = 'loss'
            else:
                result_str = 'tie'

        return MatchResult(
            match_key=f"{event_key}_{level}{match_number}",
            event_key=event_key,
            match_number=match_number,
            tournament_level=level,
            red=AllianceResult(teams=red_teams, score=red_score),
            blue=AllianceResult(teams=blue_teams, score=blue_score),
            our_alliance=our_alliance,
            our_score=our_score,
            opponent_score=opp_score,
            result=result_str,
        )

    def fetch_event_stats(self, event_key: str) -> Optional[EventStats]:
        """Fetch OPR, DPR, CCWM, and ranking for our team at this event."""
        if not self._tba_key:
            return None

        stats = EventStats()

        # OPR/DPR/CCWM
        oprs = _tba_get(f"/event/{event_key}/oprs", self._tba_key)
        if oprs and isinstance(oprs, dict):
            stats.opr = oprs.get('oprs', {}).get(self._team_key)
            stats.dpr = oprs.get('dprs', {}).get(self._team_key)
            stats.ccwm = oprs.get('ccwms', {}).get(self._team_key)

        # Rankings
        rankings = _tba_get(f"/event/{event_key}/rankings", self._tba_key)
        if rankings and isinstance(rankings, dict):
            for entry in rankings.get('rankings', []):
                if entry.get('team_key') == self._team_key:
                    stats.rank = entry.get('rank')
                    record = entry.get('record', {})
                    stats.wins = record.get('wins')
                    stats.losses = record.get('losses')
                    stats.ties = record.get('ties')
                    stats.ranking_points = entry.get('extra_stats', [None])[0]
                    break

        return stats if any(v is not None for v in vars(stats).values()) else None
