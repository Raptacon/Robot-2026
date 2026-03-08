"""
Discord webhook notifier for post-match summaries.

Requires a webhook URL in match_monitor_config.json:
    {
        "discord_webhook_url": "https://discord.com/api/webhooks/<id>/<token>"
    }

Setup: Discord server → Server Settings → Integrations → Webhooks → New Webhook → Copy URL.

Controller config hash verification:
  The robot should publish its controller config hash to NT as a string entry
  with a name matching 'controller.*hash' (case-insensitive).  The hash is
  computed as SHA-256 of the raw YAML bytes, first 8 hex characters.
  See utils/input/factory.py — publish via DataLog when config is loaded.
"""

import hashlib
import json
import logging
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .callbacks import MatchCompleteCallback
from .analyzer import MatchStats
from .quotes import format_quote

if TYPE_CHECKING:
    from .match_data_client import MatchResult, EventStats

logger = logging.getLogger("match_monitor")

_RESULT_COLORS = {
    'win':     0x57F287,   # Discord green
    'loss':    0xED4245,   # Discord red
    'tie':     0x95A5A6,   # Gray
    'unknown': 0xFEE75C,   # Yellow
}
_RESULT_EMOJI = {
    'win':     '✅',
    'loss':    '❌',
    'tie':     '➖',
    'unknown': '❓',
}


def _git_short_hash(repo_root: Path) -> Optional[str]:
    """Return current git short hash, or None on failure."""
    try:
        r = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=repo_root, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception as exc:
        logger.debug("Could not get git short hash: %s", exc)
    return None


def _git_is_clean(repo_root: Path) -> Optional[bool]:
    """Return True if working tree is clean, False if dirty, None on failure."""
    try:
        r = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=repo_root, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip() == ''
    except Exception:
        pass
    return None


def _controller_yaml_hash(repo_root: Path) -> Optional[str]:
    """SHA-256 of data/controller.yaml (first 8 hex chars), or None if missing."""
    config_path = repo_root / 'data' / 'controller.yaml'
    try:
        return hashlib.sha256(config_path.read_bytes()).hexdigest()[:8]
    except Exception:
        return None


def _teams_str(teams: list) -> str:
    """Format team list: 'frc3200, frc1234' → '3200, 1234'."""
    return ', '.join(t.replace('frc', '') for t in teams) if teams else '—'


class DiscordNotifier(MatchCompleteCallback):
    """Posts a rich embed to a Discord webhook after each match."""

    def __init__(self, webhook_url: str,
                 repo_root: Optional[Path] = None) -> None:
        self._webhook_url = webhook_url
        self._repo_root = repo_root

    @property
    def webhook_url(self) -> str:
        return self._webhook_url

    @webhook_url.setter
    def webhook_url(self, url: str) -> None:
        self._webhook_url = url.strip()

    def on_match_complete(self, match_dir: Path, metadata: dict,
                          stats: MatchStats,
                          match_result: Optional['MatchResult'] = None,
                          event_stats: Optional['EventStats'] = None) -> None:
        if not self._webhook_url:
            return
        try:
            embed = self._build_embed(metadata, stats, match_result, event_stats)
            self._post({'embeds': [embed]})
            logger.info("Discord notification sent")
        except Exception:
            logger.exception("Discord notification failed (non-fatal)")

    # ------------------------------------------------------------------
    # Embed construction
    # ------------------------------------------------------------------

    def _build_embed(self, metadata: dict, stats: MatchStats,
                     match_result: Optional['MatchResult'],
                     event_stats: Optional['EventStats']) -> dict:
        match_type = metadata.get('match_type', 'Match')
        match_number = metadata.get('match_number', '?')
        event_name = metadata.get('event_name', '')

        result_str = (match_result.result if match_result else 'unknown') or 'unknown'
        emoji = _RESULT_EMOJI.get(result_str, '❓')
        color = _RESULT_COLORS.get(result_str, _RESULT_COLORS['unknown'])

        # Title
        type_label = match_type.capitalize() if match_type else 'Match'
        title = f"{type_label} {match_number} — {result_str.upper()} {emoji}"
        if event_name:
            title = f"[{event_name.upper()}] {title}"

        fields = []

        # --- Score + alliances ---
        if match_result:
            our = (match_result.our_alliance or '').upper()
            opp = 'BLUE' if our == 'RED' else 'RED' if our == 'BLUE' else '?'
            our_score = match_result.our_score if match_result.our_score is not None else '?'
            opp_score = match_result.opponent_score if match_result.opponent_score is not None else '?'
            fields.append({
                'name': '🏁 Score',
                'value': f"**{our or '?'}** {our_score} — {opp_score} **{opp}**",
                'inline': True,
            })
            fields.append({
                'name': '🔴 Red Alliance',
                'value': _teams_str(match_result.red.teams),
                'inline': True,
            })
            fields.append({
                'name': '🔵 Blue Alliance',
                'value': _teams_str(match_result.blue.teams),
                'inline': True,
            })

        # --- Battery ---
        v = stats
        if v.avg_voltage is not None:
            parts = []
            if v.start_voltage is not None:
                parts.append(f"Start **{v.start_voltage}V**")
            if v.avg_voltage is not None:
                parts.append(f"Avg **{v.avg_voltage}V**")
            if v.min_voltage is not None:
                parts.append(f"Min **{v.min_voltage}V**")
            fields.append({
                'name': '🔋 Battery',
                'value': ' · '.join(parts),
                'inline': True,
            })

        # --- Brownouts ---
        if v.brownout_count > 0:
            ts = ', '.join(f"{t}s" for t in v.brownout_timestamps_sec[:5])
            extra = f' (+{v.brownout_count - 5} more)' if v.brownout_count > 5 else ''
            bo_val = f"**{v.brownout_count}** @ {ts}{extra}"
        else:
            bo_val = "None ✅"
        fields.append({'name': '⚡ Brownouts', 'value': bo_val, 'inline': True})

        # --- Disconnects ---
        if v.disconnect_count > 0:
            ts = ', '.join(f"{t}s" for t in v.disconnect_timestamps_sec[:3])
            extra = f' (+{v.disconnect_count - 3} more)' if v.disconnect_count > 3 else ''
            fields.append({
                'name': '🔌 Disconnects',
                'value': f"**{v.disconnect_count}** @ {ts}{extra}",
                'inline': True,
            })

        # --- DS log stats ---
        if stats.ds_log and stats.ds_log.records:
            ds = stats.ds_log
            if ds.avg_packet_loss_pct is not None:
                fields.append({
                    'name': '📡 Packet Loss',
                    'value': f"**{ds.avg_packet_loss_pct}%**",
                    'inline': True,
                })
            if ds.avg_trip_time_ms is not None:
                fields.append({
                    'name': '⏱ Latency',
                    'value': f"avg **{ds.avg_trip_time_ms}ms** / max **{ds.max_trip_time_ms}ms**",
                    'inline': True,
                })

        # --- OPR / rank ---
        if event_stats:
            es = event_stats
            opr_parts = []
            if es.opr is not None:
                opr_parts.append(f"OPR **{es.opr:.1f}**")
            if es.dpr is not None:
                opr_parts.append(f"DPR **{es.dpr:.1f}**")
            if es.ccwm is not None:
                opr_parts.append(f"CCWM **{es.ccwm:.1f}**")
            if opr_parts:
                fields.append({
                    'name': '📊 Event Stats',
                    'value': ' · '.join(opr_parts),
                    'inline': True,
                })
            if es.rank is not None:
                record = ''
                if es.wins is not None:
                    record = f" ({es.wins}W-{es.losses}L-{es.ties}T"
                    if es.ranking_points is not None:
                        record += f", {es.ranking_points:.0f} RP"
                    record += ")"
                fields.append({
                    'name': '🏆 Rank',
                    'value': f"**#{es.rank}**{record}",
                    'inline': True,
                })

        # --- Code / controller hash ---
        if self._repo_root:
            git_hash = _git_short_hash(self._repo_root)
            if git_hash:
                is_clean = _git_is_clean(self._repo_root)
                dirty = '' if is_clean else ' ⚠ dirty'
                fields.append({
                    'name': '🔧 Robot Code',
                    'value': f"`{git_hash}`{dirty}",
                    'inline': True,
                })

            if stats.controller_config_hash:
                local_hash = _controller_yaml_hash(self._repo_root)
                if local_hash is not None:
                    match_icon = '✅' if local_hash == stats.controller_config_hash else '⚠ mismatch'
                    fields.append({
                        'name': '🎮 Controller Config',
                        'value': f"`{stats.controller_config_hash}` {match_icon}",
                        'inline': True,
                    })
                else:
                    fields.append({
                        'name': '🎮 Controller Config',
                        'value': f"`{stats.controller_config_hash}`",
                        'inline': True,
                    })

        # --- Links ---
        links = []
        if match_result and match_result.match_key:
            links.append(
                f"[Blue Alliance](https://www.thebluealliance.com/match/{match_result.match_key})"
            )
        if match_result and match_result.event_key:
            year = match_result.event_key[:4]
            code = match_result.event_key[4:]
            links.append(
                f"[FRC Events](https://frc-events.firstinspires.org/{year}/{code})"
            )
        if match_result and match_result.video_url:
            links.append(f"[Match Video]({match_result.video_url})")
        if links:
            fields.append({
                'name': '🔗 Links',
                'value': ' · '.join(links),
                'inline': False,
            })

        # --- Quote ---
        fields.append({
            'name': '\u200b',   # zero-width space separator
            'value': format_quote(),
            'inline': False,
        })

        embed = {
            'title': title,
            'color': color,
            'fields': fields,
            'footer': {
                'text': f"Team 3200 Raptacon · {datetime.now():%Y-%m-%d %H:%M:%S}",
            },
        }
        # Clickable title → TBA event page
        if match_result and match_result.event_key:
            embed['url'] = (
                f"https://www.thebluealliance.com/event/{match_result.event_key}"
            )

        return embed

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _post(self, payload: dict) -> None:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            self._webhook_url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'DiscordBot (https://github.com/Raptacon/Robot-2026, 1.0)',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    logger.warning(f"Discord webhook returned {resp.status}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors='replace')[:200]
            logger.warning(f"Discord webhook HTTP error {e.code}: {body}")
        except urllib.error.URLError as e:
            logger.debug(f"Discord webhook unreachable: {e.reason}")
