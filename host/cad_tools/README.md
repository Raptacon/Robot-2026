# CAD Tools

Helper scripts and storage for robot CAD models used by the camera visualizer.

## Layout

```
host/cad_tools/
  convert_step.py   - STEP -> GLTF/GLB converter (FreeCAD or trimesh)
  models/           - Drop .glb/.gltf files here (gitignored, large binaries)
  README.md
```

## Getting CAD Models

The camera visualizer (`host/camera_visualizer/`) reads from `models/`.
There are two ways to populate it:

### Option 1: Export GLTF/GLB directly from Onshape (recommended)

1. Open the assembly in Onshape
2. Right-click the assembly tab > Export > GLTF
3. Save to `host/cad_tools/models/`
4. Refresh the visualizer, click "Load CAD"

### Option 2: Convert from STEP

If you only have a STEP file:

```bash
python host/cad_tools/convert_step.py input.step models/output.glb
```

Requires one of:
- **FreeCAD** headless (`FreeCADcmd` on PATH) — best assembly fidelity
- **trimesh + cascadio** — `pip install trimesh[easy] cascadio`

## Storage

`models/` is gitignored to keep the repo small. Large CAD binaries live in
a separate team CAD repo (TBD). Each developer maintains their own local
copy under `models/`.

## Visualizer Integration

The camera visualizer's `serve.py` looks at `CAD_DIR = host/cad_tools/models/`.
The "Load CAD" button scans this directory and lists available models.
See `host/camera_visualizer/CLAUDE.md` for the full visualizer architecture.
