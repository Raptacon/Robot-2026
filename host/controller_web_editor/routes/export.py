"""Server-side PNG/PDF export wired to :mod:`host.controller_config.print_render`.

The frontend POSTs cannot stream binaries cleanly, so this endpoint is
``GET``-able and returns the rendered file with a download disposition.
Same shape as ``--export`` on the Tkinter CLI — pipelines can curl this
endpoint to bake printable assets.

Only YAML files under :mod:`host.controller_web_editor.paths` are
accepted; the caller passes the same ``path`` parameter used by
``/api/config``.
"""

from __future__ import annotations

from pathlib import Path

from host.controller_config.print_render import render_to_bytes
from utils.controller.config_io import load_config


ALLOWED_ORIENTATIONS = frozenset({"portrait", "landscape"})
ALLOWED_FORMATS = frozenset({"png", "pdf"})

MIME = {
    "png": "image/png",
    "pdf": "application/pdf",
}


class ExportRequestError(ValueError):
    """Bad client-supplied export parameters (orientation, format)."""


def _icon_loader():
    """Reuse the Tkinter tool's icon loader if available; otherwise None.

    Print output benefits from the small button glyphs but they aren't
    required — ``print_render`` falls back to text-only labels.
    """
    try:
        from host.controller_config.icon_loader import InputIconLoader
        from host.controller_config.main import _get_project_root
    except Exception:
        return None
    icons_dir = (_get_project_root()
                 / "images" / "XboxControlIcons" / "Buttons Full Solid")
    if not icons_dir.is_dir():
        return None
    try:
        return InputIconLoader(icons_dir)
    except Exception:
        return None


def export_from_yaml(
    yaml_path: Path,
    orientation: str,
    fmt: str,
    hide_unassigned: bool = False,
) -> tuple[bytes, str, str]:
    """Render an export from a YAML file on disk.

    Returns ``(bytes, content_type, suggested_filename)``.  Raises
    :class:`ExportRequestError` for bad orientation/format, or whatever
    ``load_config`` / ``render_to_bytes`` raise for missing or
    inconsistent configs.
    """
    orientation = orientation.lower()
    fmt = fmt.lower().lstrip(".")
    if orientation not in ALLOWED_ORIENTATIONS:
        raise ExportRequestError(
            f"orientation must be one of {sorted(ALLOWED_ORIENTATIONS)}; "
            f"got {orientation!r}")
    if fmt not in ALLOWED_FORMATS:
        raise ExportRequestError(
            f"format must be one of {sorted(ALLOWED_FORMATS)}; got {fmt!r}")

    config = load_config(yaml_path)
    data = render_to_bytes(
        config, orientation, fmt,
        label_positions=None,
        hide_unassigned=hide_unassigned,
        icon_loader=_icon_loader(),
    )
    stem = yaml_path.stem or "controllers"
    filename = f"{stem}_{orientation}.{fmt}"
    return data, MIME[fmt], filename


__all__ = [
    "ALLOWED_FORMATS",
    "ALLOWED_ORIENTATIONS",
    "ExportRequestError",
    "MIME",
    "export_from_yaml",
]
