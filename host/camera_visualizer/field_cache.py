"""
Field asset cache: downloads AdvantageScope field bundles from GitHub
and extracts individual field models (GLB + config.json).

Cached locally in cache/fields/<field-id>/.
"""

import io
import json
import os
import urllib.request
import zipfile

BUNDLE_URL = (
    'https://github.com/Mechanical-Advantage/AdvantageScopeAssets'
    '/releases/download/bundles-v1/AllAssetsDefaultFRC.zip'
)

# Curated field definitions — id maps to zip entry in the bundle
FIELD_LIST = [
    {
        'id': 'robot-view',
        'name': 'Robot View',
        'description': 'Robot at origin with AprilTag ring',
        'type': 'builtin',
    },
    {
        'id': '2026-field',
        'name': '2026 Field',
        'description': '2026 FRC Rebuilt field',
        'zipEntry': 'Field3d_2026FRCFieldV1.zip',
        'type': 'field',
    },
    {
        'id': '2025-welded',
        'name': '2025 Field (Welded)',
        'description': '2025 FRC field, welded variant',
        'zipEntry': 'Field3d_2025FRCFieldWeldedV2.zip',
        'type': 'field',
    },
    {
        'id': '2025-andymark',
        'name': '2025 Field (AndyMark)',
        'description': '2025 FRC field, AndyMark variant',
        'zipEntry': 'Field3d_2025FRCFieldAndyMarkV2.zip',
        'type': 'field',
    },
    {
        'id': '2024-field',
        'name': '2024 Field',
        'description': '2024 FRC field',
        'zipEntry': 'Field3d_2024FRCFieldV3.zip',
        'type': 'field',
    },
    {
        'id': 'cat-box',
        'name': 'Cat Box',
        'description': 'Meow',
        'type': 'builtin',
    },
]


class FieldCache:
    """Manages downloading and caching of FRC field models."""

    def __init__(self, cache_dir: str, bundle_cache_path: str = None):
        self.cache_dir = cache_dir
        self.bundle_path = bundle_cache_path or os.path.join(
            os.path.dirname(cache_dir), 'frc_assets.zip'
        )

    def get_field_list(self) -> list:
        return FIELD_LIST

    def get_field_info(self, field_id: str) -> dict:
        """Look up a field by id. Returns None if not found."""
        return next((f for f in FIELD_LIST if f['id'] == field_id), None)

    def ensure_bundle(self) -> bool:
        """Download the asset bundle if not cached. Returns True on success."""
        if os.path.isfile(self.bundle_path):
            return True
        os.makedirs(os.path.dirname(self.bundle_path), exist_ok=True)
        try:
            print(f'Downloading field assets from GitHub...')
            urllib.request.urlretrieve(BUNDLE_URL, self.bundle_path)
            print(f'Downloaded to {self.bundle_path}')
            return True
        except Exception as e:
            print(f'Failed to download assets: {e}')
            return False

    def extract_field(self, field_id: str):
        """Extract a field's model.glb and config.json.

        Returns (config_dict, glb_bytes) or (None, None) on failure.
        """
        info = self.get_field_info(field_id)
        if not info or 'zipEntry' not in info:
            return None, None

        # Check local cache
        field_dir = os.path.join(self.cache_dir, field_id)
        glb_path = os.path.join(field_dir, 'model.glb')
        config_path = os.path.join(field_dir, 'config.json')

        if os.path.isfile(glb_path) and os.path.isfile(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            with open(glb_path, 'rb') as f:
                glb = f.read()
            return config, glb

        # Extract from bundle
        if not self.ensure_bundle():
            return None, None

        try:
            outer = zipfile.ZipFile(self.bundle_path)
            inner_data = outer.read(info['zipEntry'])
            inner = zipfile.ZipFile(io.BytesIO(inner_data))

            config = json.loads(inner.read('config.json'))
            glb = inner.read('model.glb')

            # Cache locally
            os.makedirs(field_dir, exist_ok=True)
            with open(config_path, 'w') as f:
                json.dump(config, f)
            with open(glb_path, 'wb') as f:
                f.write(glb)

            return config, glb
        except Exception as e:
            print(f'Failed to extract field {field_id}: {e}')
            return None, None
