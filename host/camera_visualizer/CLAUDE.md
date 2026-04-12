# Camera Visualizer

Three.js web app for visualizing robot geometry, CAD models, and FRC fields.

## Running

```bash
python -m host.camera_visualizer.serve   # serves on localhost:8070
```

Server auto-reloads `constants/robot_geometry.py` on each browser refresh. No restart needed for geometry changes. Ctrl+C exits instantly.

## Module Structure

```
host/camera_visualizer/
  serve.py              — thin HTTP router, delegates to route modules
  field_cache.py        — downloads AdvantageScope bundles from GitHub, extracts/caches
  routes/
    config.py           — robot config JSON from constants/robot_geometry.py, page building
    fields.py           — AprilTag field layout extraction from robotpy_apriltag
    cad.py              — CAD model listing and serving from cad/ directory
    points.py           — field measurement point persistence (data/field_points.json)
  cad_loader.js         — GLTF/GLB loader with DRACO, mesh optimization, part tree, selection
  field_loader.js       — field model loading, scene mode switching, AprilTag placement
  index.html            — Three.js scene, viewports, sidebar, all UI
  tests/
    test_routes.py      — 30 tests for route modules and field cache
```

## Scene Modes

- **Robot View** (default) — robot at origin, configurable AprilTag ring
- **FRC Field views** (2024-2026) — AdvantageScope field models with real AprilTag positions
- **Cat Box** — cat faces on cube walls around robot (easter egg)

## Coordinate Systems

- **Scene/Robot**: WPI standard — +X forward, +Y left, +Z up. Origin at robot center.
- **Field (WPILib NWU)**: Origin at blue alliance wall corner. +X toward red wall, +Y left, +Z up.
- **Field (AdvantageScope "wall-blue")**: Origin at field center. Offset to WPILib NWU on load.
- **GLTF models**: Y-up per spec. Onshape exports need 90deg X tilt + 180deg Z yaw.

## CAD Model Loading

- Loads GLTF/GLB via Three.js GLTFLoader + DRACOLoader
- Auto-detects units: >20 = inches, >200 = mm, else meters
- Orientation: `_xSteps=1` (90deg X), `_yawSteps=2` (180deg Z) for Onshape exports
- Merges 16K+ draw calls into ~100-200 by grouping per named CAD part (BufferGeometryUtils)
- Replaces PBR materials with MeshPhongMaterial for performance
- Part tree overlay with checkboxes for visibility
- Click-to-select with bounding box, center marker (sphere + RGB axes + face dots)
- Ctrl+click selected part to hide, Ctrl+Z undo, Ctrl+Y redo, Escape clears selection
- Shift+click in 3D viewport for multi-select
- Ctrl+click in tree for multi-select/deselect

## Field Asset Pipeline

AdvantageScope ships field GLB models in a ~100MB zip bundle on GitHub releases:
`Mechanical-Advantage/AdvantageScopeAssets/releases/download/bundles-v1/AllAssetsDefaultFRC.zip`

Structure: outer zip contains per-field inner zips (e.g. `Field3d_2026FRCFieldV1.zip`),
each containing `config.json` + `model.glb`.

- Bundle downloaded on first field request, cached at `cache/frc_assets.zip`
- Individual fields extracted and cached at `cache/fields/<field-id>/`
- Config includes: name, coordinate system, rotations, dimensions, AprilTag positions, game pieces
- AprilTag positions from config use field-center origin; `robotpy_apriltag` provides WPILib NWU positions

## Robot Geometry Architecture

**Single source of truth:** `constants/robot_geometry.py`
- Robot frame dimensions (meters)
- Swerve positions: define FL, derive FR/BL/BR by mirroring
- Cameras via `make_camera()` with inches + intuitive degrees
- Mechanisms via `MechanismMount` with parent-relative transform chaining

**Helpers:** `utils/geometry.py`
- `transform_from_inches()` — general Transform3d builder (pitch_up negated for WPI)
- `chain_transforms()` — compose parent-to-child transforms via Pose3d
- `CameraGeometry` — camera with Transform3d + FOV + serialization
- `MechanismMount` — mechanism with transform, parent chaining, visualization metadata

**Downstream consumers:**
- `constants/swerve_constants.py` — derives `moduleFrontLeftX` etc. from `SWERVE_FL.X()`
- `subsystem/localization/localization.py` — imports `CAMERAS` for vision processing
- `host/camera_visualizer/serve.py` — serializes to JSON for the web visualizer

## Key Design Decisions

- All robot values in WPILib types (Transform3d, Translation2d) — not raw floats
- `utils/geometry.py` is WPILib-dependent but separated from constants (reusable classes)
- Robot geometry in `THREE.Group` (robotGroup) for field placement; environment in envGroup
- Field assets fetched on demand, not stored in repo (cache/ is gitignored)
- CAD files (.glb, .gltf, .step) will live in a separate team CAD repo
- Visualizer tests live with the module, not in robot tests/ directory
- serve.py is stdlib-only Python (no Flask/FastAPI) for zero-dependency host tools

## Tests

```bash
# Visualizer tests only (fast, no robot sim needed)
pytest host/camera_visualizer/tests/ -v

# Robot geometry tests (in robot test suite)
python -m robotpy test -- tests/test_geometry.py -v
```

## Adding a Camera or Mechanism

1. Edit `constants/robot_geometry.py`
2. Add a `make_camera(...)` or `MechanismMount(...)` entry
3. For chained mechanisms: define parent transform, pass as `parent_transform` kwarg
4. Refresh the browser — visualizer picks up changes automatically
