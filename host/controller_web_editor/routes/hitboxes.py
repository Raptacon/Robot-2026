"""GET/POST handler logic for controller hitbox layouts.

Layouts live as JSON files under ``host/controller_web_editor/hitboxes/``,
one per controller type.  v1 only ships ``xbox.json``.  Layout names are
allowlisted so the URL parameter can't traverse the filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path


HITBOXES_DIR = Path(__file__).resolve().parent.parent / "hitboxes"

# Allowlist of layout names that may be read/written.  Extend with
# "ps5", "switch", etc. when those layouts arrive.
ALLOWED_LAYOUTS = frozenset({"xbox"})


class LayoutNotAllowedError(ValueError):
    """Raised when the client requests an unknown layout name."""


def _layout_path(layout: str) -> Path:
    if layout not in ALLOWED_LAYOUTS:
        raise LayoutNotAllowedError(f"unknown layout: {layout!r}")
    return HITBOXES_DIR / f"{layout}.json"


def load_layout(layout: str) -> dict:
    """Read a hitbox JSON file and return it as a dict."""
    return json.loads(_layout_path(layout).read_text(encoding="utf-8"))


def save_layout(layout: str, data: dict) -> None:
    """Write a hitbox JSON file.  Validates the payload shape minimally.

    A timestamp-free ``.bak`` of the previous contents is written next to
    the file before overwriting, so an accidental overwrite is recoverable.
    """
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    if "regions" not in data or not isinstance(data["regions"], dict):
        raise ValueError("payload missing 'regions' object")
    if "viewBox" not in data or not isinstance(data["viewBox"], str):
        raise ValueError("payload missing 'viewBox' string")

    # Optional fields validated only if present.
    labels = data.get("labels")
    if labels is not None and not isinstance(labels, dict):
        raise ValueError("'labels' must be an object")
    fonts = data.get("fonts")
    if fonts is not None and not isinstance(fonts, dict):
        raise ValueError("'fonts' must be an object")

    path = _layout_path(layout)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_bytes(path.read_bytes())

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def list_layouts() -> list[str]:
    """Return all allowlisted layouts that currently have a file on disk."""
    return sorted(
        name for name in ALLOWED_LAYOUTS
        if (HITBOXES_DIR / f"{name}.json").is_file()
    )
