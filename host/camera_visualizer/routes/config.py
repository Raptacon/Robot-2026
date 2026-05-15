"""Robot config and page building routes."""

import importlib
import json
import os

_IN = 0.0254


def reload_geometry():
    """Re-import robot_geometry so edits are picked up on browser refresh."""
    import constants.robot_geometry as geo
    importlib.reload(geo)
    return geo


def build_config_json() -> str:
    """Build the JSON config blob for the visualizer."""
    geo = reload_geometry()
    config = {
        "robot_frame": {
            "width_inches": round(geo.ROBOT_WIDTH_M / _IN, 2),
            "length_inches": round(geo.ROBOT_LENGTH_M / _IN, 2),
            "width_meters": round(geo.ROBOT_WIDTH_M, 4),
            "length_meters": round(geo.ROBOT_LENGTH_M, 4),
        },
        "cameras": [cam.to_dict() for cam in geo.CAMERAS],
        "mechanisms": [mech.to_dict() for mech in geo.MECHANISMS],
    }
    return json.dumps(config, indent=2)


def build_page(html_dir: str) -> bytes:
    """Read index.html and inject the config JSON."""
    html_path = os.path.join(html_dir, 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    config_json = build_config_json()
    inject = f'<script>window.__ROBOT_CONFIG__ = {config_json};</script>\n'
    html = html.replace(
        '<script type="module">',
        inject + '<script type="module">',
        1,
    )
    return html.encode('utf-8')
