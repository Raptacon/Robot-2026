"""CAD model file routes."""

import os


def list_cad_models(cad_dir: str) -> list:
    """Scan host/cad_tools/models/ directory for loadable model files."""
    models = []
    if os.path.isdir(cad_dir):
        for fname in sorted(os.listdir(cad_dir)):
            if fname.lower().endswith(('.glb', '.gltf')):
                size = os.path.getsize(os.path.join(cad_dir, fname))
                models.append({
                    'name': fname,
                    'url': f'/cad/{fname}',
                    'size': size,
                })
    return models


def serve_cad_file(cad_dir: str, filename: str):
    """Read a CAD file. Returns (data, mime_type) or (None, None)."""
    fname = os.path.basename(filename)
    if not fname.lower().endswith(('.glb', '.gltf', '.bin')):
        return None, None
    fpath = os.path.join(cad_dir, fname)
    if not os.path.isfile(fpath):
        return None, None
    with open(fpath, 'rb') as f:
        data = f.read()
    mime = {
        '.glb': 'model/gltf-binary',
        '.gltf': 'model/gltf+json',
        '.bin': 'application/octet-stream',
    }.get(os.path.splitext(fname)[1].lower(), 'application/octet-stream')
    return data, mime
