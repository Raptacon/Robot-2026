"""Field measurement point persistence."""

import json
import os


def load_points(points_file: str) -> str:
    """Read saved points. Returns JSON string."""
    if os.path.isfile(points_file):
        with open(points_file, 'r') as f:
            return f.read()
    return '{"points":[]}'


def save_points(points_file: str, data: bytes) -> None:
    """Write points data to file."""
    os.makedirs(os.path.dirname(points_file), exist_ok=True)
    with open(points_file, 'wb') as f:
        f.write(data)
