# Camera Visualizer

Three.js web app for visualizing robot geometry, CAD models, FRC fields, and
camera coverage. Used to verify camera/mechanism positions, measure transforms
to field points, and check AprilTag detection coverage.

## Running

```bash
python -m host.camera_visualizer.serve   # serves on localhost:8070
```

Server auto-reloads `constants/robot_geometry.py` on each browser refresh.
No restart needed for geometry changes. Ctrl+C exits instantly.

## Module Structure

```
host/camera_visualizer/
  serve.py              — thin HTTP router, delegates to route modules
  field_cache.py        — downloads AdvantageScope bundles from GitHub, extracts/caches
  routes/
    config.py           — robot config JSON from constants/robot_geometry.py, page building
    fields.py           — AprilTag field layout extraction from robotpy_apriltag
    cad.py              — CAD model listing and serving from cad/ directory
    points.py           — field measurement point persistence (named sets)
  cad_loader.js         — GLTF/GLB loader with DRACO, mesh optimization, part tree
  field_loader.js       — field model loading, scene modes, AprilTag placement, selection
  point_manager.js      — field measurement points with persistence
  index.html            — Three.js scene, viewports, sidebar, all UI wiring
  tests/
    test_routes.py      — 34 tests for route modules and field cache
```

## Scene Modes

Selectable via dropdown in the header. All modes show the robot + CAD overlay
on the configured background:

- **Robot View** (default) — robot at origin, AprilTag ring around robot
- **Evergreen Field** — programmatic FRC field perimeter (no game elements)
- **2024-2026 Fields** — full AdvantageScope field models with game elements
- **Cat Box** — cat faces on cube walls (easter egg)

Switching modes:
- Hides/shows the appropriate environment
- Repositions robot to field center (or origin for Robot View)
- Adjusts camera views to fit the field
- Adjusts lighting (lower intensity for robot view, higher for field)
- Loads real AprilTag positions from `robotpy_apriltag` for field modes

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
- Part tree overlay (left side of perspective viewport, collapsible)
- Click to select with bounding box + center marker (sphere + RGB axes + face dots)
- **Tilt 90 / Rot 90** buttons for orientation correction
- **Opacity slider** for transparency
- **BBox** checkbox toggles bounding box display

### CAD Selection Shortcuts

- **Click** — select single part (clears previous)
- **Shift+click in viewport** — add/remove part from multi-selection
- **Ctrl+click in tree** — multi-select/deselect
- **Click in tree** — select assembly (combined bounding box of all child parts)
- **Ctrl+click selected part** — hide it
- **Ctrl+Z** — undo last hide
- **Ctrl+Y** — redo hide
- **Escape** — clear all selections

### CAD Sidebar Info

Shows the selected component with:
- Bounding box center (X, Y, Z) in current display units
- Bounding box dimensions (Width, Length, Height)
- `transform_from_inches(...)` code snippet (robot-relative) with Copy button
- `Translation3d(...)` code snippet (meters) with Copy button

## Field Asset Pipeline

AdvantageScope ships field GLB models in a ~100MB zip bundle on GitHub releases:
`Mechanical-Advantage/AdvantageScopeAssets/releases/download/bundles-v1/AllAssetsDefaultFRC.zip`

Structure: outer zip contains per-field inner zips (e.g. `Field3d_2026FRCFieldV1.zip`),
each containing `config.json` + `model.glb`.

- Bundle downloaded on first field request, cached at `cache/frc_assets.zip`
- Individual fields extracted and cached at `cache/fields/<field-id>/`
- Config includes: name, coordinate system, rotations, dimensions, AprilTag positions, game pieces
- AprilTag positions from `robotpy_apriltag.AprilTagFieldLayout.loadField()` (WPILib NWU)

## Field Element Selection

Click any field surface to mark a point at the click location:
- Orange sphere + crosshair shown at the clicked point
- Sidebar shows field coordinates and robot-relative transform
- Distance from robot center displayed
- Copy buttons for `Translation3d` and `transform_from_inches`

Point-based picking avoids selecting entire combined meshes
(useful since field GLBs often combine many elements into single meshes).

## Field Points (Measurement Markers)

User-placeable measurement points persisted across sessions.

### Creating Points

- Click **+ Add** in the Field Points panel — cursor becomes crosshair
- Click anywhere on the field/ground to place a green sphere with label
- Point shows label, vertical line to ground, X/Y/Z coordinates

### Editing Points

- **Click a point** in 3D or its name in the sidebar list to select
- **Rename**: edit the name field (live rename as you type, Escape reverts)
- **Height slider**: adjust Z position with the slider
- **× button** in list: delete a point
- **Ctrl+click selected** is reserved for hiding (CAD), not points

### Named Point Sets

- **Set dropdown**: switch between named sets — auto-loads on change
- **Save** — write current points to selected set
- **Load** — reload selected set from disk
- **New** — create empty set with custom name

Sets persisted to `data/field_points/<safe_name>.json`. Useful for storing
named groups like "Red Targets" vs "Blue Targets" or game-piece locations.

## Robot Movement

In field modes, the robot can be repositioned to test camera coverage:

### Sidebar Panel ("Robot Position")

- **X / Y inputs** — meters from field origin (blue wall corner)
- **Heading slider** — 0-360° rotation around Z
- **Heading input** — exact degree entry

### Mouse Controls

- **Shift+left-drag** on top-down view — move robot to cursor position
- Inputs sync automatically as the robot moves

Sim camera views in the sidebar follow the robot's world transform and
re-render every 10 frames showing the actual coverage.

## AprilTag Detection Modeling

The visualizer simulates realistic AprilTag detection limits:

### FOV Cone Zones (per camera)

- **Green** (0-4m) — reliable detection (matches `vision_single_tag_max_distance_m`)
- **Yellow** (4-6m) — marginal, high ambiguity (multi-tag may work)
- **Red** (6-8m) — unlikely to detect

### Tag Filtering Rules

A tag is reported visible only if:
1. Inside the camera's FOV frustum
2. Within 6m of the camera (max detection range)
3. Not occluded by field geometry (line-of-sight raycast)
4. Tag face is within 60° of head-on (not edge-on)

### Display

- **Sidebar** under each camera: green=reliable IDs, yellow=marginal?, red=blocked
- **3D tags** colored: green=reliable, yellow=marginal, orange-red=blocked, white=not seen
- Real-time updates as the robot moves on the field

See `subsystem/localization/VISION.md` for details on these thresholds.

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
- PBR materials on field models capped at metalness=0.3 so ambient lighting works

## Lighting

Adjustable per scene mode (`setLightingMode`):
- **Robot mode**: ambient 0.8, hemisphere 0.5, directional 0.8 (soft, prevents blowout)
- **Field mode**: ambient 1.2, hemisphere 1.5, directional 0.6 (brighter for large area)

No environment map — caused top-down blowout. PBR materials on field models
have their metalness reduced to 0.3 max so they respond to ambient light
correctly instead of reflecting (missing) environment.

## Tests

```bash
# Visualizer tests only (fast, no robot sim needed)
pytest host/camera_visualizer/tests/ -v

# Robot geometry tests (in robot test suite)
python -m robotpy test -- tests/test_geometry.py -v
```

34 tests cover: config JSON structure, field cache extraction (with fake
test bundles), AprilTag layout, CAD listing and serving with path traversal
protection, point set persistence.

## Adding a Camera or Mechanism

1. Edit `constants/robot_geometry.py`
2. Add a `make_camera(...)` or `MechanismMount(...)` entry
3. For chained mechanisms: define parent transform, pass as `parent_transform` kwarg
4. Refresh the browser — visualizer picks up changes automatically

## Adding a New Scene Mode

1. Add entry to `FIELD_LIST` in `field_cache.py` with `type: 'builtin'` (no zipEntry)
2. Add branch in `field_loader.js`'s `setMode()` to build/load the scene
3. Set `this.fieldConfig` and fire `onFieldLoaded` callback for camera fit

## Version Indicator

Header shows the current visualizer version (v##) next to the title.
Bump it when making changes so users know if they're seeing latest code.
