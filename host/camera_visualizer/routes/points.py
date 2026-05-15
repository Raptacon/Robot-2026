"""Field measurement point persistence with named sets."""

import json
import os
import re


def _safe_name(name: str) -> str:
    """Sanitize set name for use as filename."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)


def _set_path(points_dir: str, set_name: str) -> str:
    """Get the file path for a named point set."""
    safe = _safe_name(set_name)
    return os.path.join(points_dir, f'{safe}.json')


def load_points(points_dir: str, set_name: str = 'default') -> str:
    """Read saved points for a named set. Returns JSON string."""
    fpath = _set_path(points_dir, set_name)
    if os.path.isfile(fpath):
        with open(fpath, 'r') as f:
            return f.read()
    return '{"name":"' + set_name + '","points":[]}'


def save_points(points_dir: str, set_name: str, data: bytes) -> None:
    """Write points data to a named set file."""
    os.makedirs(points_dir, exist_ok=True)
    fpath = _set_path(points_dir, set_name)
    with open(fpath, 'wb') as f:
        f.write(data)


def list_point_sets(points_dir: str) -> list:
    """List available point set names."""
    sets = []
    if os.path.isdir(points_dir):
        for fname in sorted(os.listdir(points_dir)):
            if fname.endswith('.json'):
                name = fname[:-5]
                fpath = os.path.join(points_dir, fname)
                try:
                    with open(fpath, 'r') as f:
                        data = json.load(f)
                    sets.append({
                        'name': data.get('name', name),
                        'file': name,
                        'count': len(data.get('points', [])),
                    })
                except (json.JSONDecodeError, OSError):
                    sets.append({'name': name, 'file': name, 'count': 0})
    return sets
