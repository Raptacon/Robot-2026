"""Server-side user preferences for the web editor.

Keeps a tiny JSON file alongside the server module so settings (theme,
later UI toggles) survive server restarts without leaning on the
browser's localStorage.  This is *per server install*, not per user --
fine for a single-user dev tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PREFS_PATH = Path(__file__).resolve().parent.parent / "prefs.json"

# Only these keys are accepted from clients.  Unknown keys are dropped
# silently so a stale frontend can't smuggle arbitrary data into the
# prefs file.
KNOWN_KEYS = frozenset({"theme"})

# Allowed values per key, where applicable.  Theme names must match the
# `data-theme` attribute values understood by app.css.
ALLOWED_THEMES = frozenset({
    "dark", "light", "raptacon", "solarized-dark", "high-contrast",
})


def _validate(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in KNOWN_KEYS:
            continue
        if key == "theme":
            if not isinstance(value, str) or value not in ALLOWED_THEMES:
                raise ValueError(
                    f"invalid theme {value!r}; "
                    f"allowed: {sorted(ALLOWED_THEMES)}")
            out["theme"] = value
    return out


def load_prefs() -> dict[str, Any]:
    """Return the persisted preferences, or {} if the file is missing.

    Corrupt files are treated as empty -- preferences are not load-
    bearing, and a single malformed write shouldn't break the UI.
    """
    if not PREFS_PATH.is_file():
        return {}
    try:
        data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Filter to known keys on read so a previously-valid file with
    # newer keys doesn't surprise us.
    return {k: v for k, v in data.items() if k in KNOWN_KEYS}


def save_prefs(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge ``payload`` into the prefs file and return the new state.

    Raises ``ValueError`` if ``payload`` contains invalid values.
    Unknown keys are silently dropped.
    """
    incoming = _validate(payload)
    current = load_prefs()
    current.update(incoming)
    PREFS_PATH.write_text(
        json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return current


__all__ = ["ALLOWED_THEMES", "KNOWN_KEYS", "load_prefs", "save_prefs"]
