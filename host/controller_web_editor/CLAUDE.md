# Controller Web Editor

Web-app replacement for the Tkinter tool in [host/controller_config/](../controller_config). Edits the same YAML (`data/inputs/controller.yaml` and friends) and produces identical printable output via the existing PIL pipeline.

## Goals

1. Create / edit actions (CRUD with validation)
2. Assign actions to inputs via a menu (keyboard-navigable)
3. Assign actions on a graphical 2D Xbox controller (SVG + hit-region overlay)
4. Live input/output simulation for the selected action
5. Load / save `FullConfig` YAML — schema unchanged
6. Generate printable PNG/PDF graphics of the current config
7. Modern UX: undo/redo, search, keyboard nav, deep links, responsive

## Non-goals (v1)

- 3D controller view. Existing `images/xbox-controller-black/source/xbox.glb` is a single fused mesh with no per-button nodes, so the "free hit-testing" advantage doesn't apply. Revisit if a rigged model surfaces.
- Direct robot deploy from the editor.
- Replacing the YAML schema. [utils/controller/model.py](../../utils/controller/model.py) + [utils/controller/config_io.py](../../utils/controller/config_io.py) stay authoritative.
- Serving files outside `data/`. Path widening is a one-line change in `paths.py`.

## Architecture

Follows the [host/camera_visualizer](../camera_visualizer) pattern: small Python HTTP server alongside a Svelte SPA. Run with `python -m host.controller_web_editor`.

```
host/controller_web_editor/
  __main__.py
  serve.py                 # stdlib http.server entry
  paths.py                 # safe_resolve(); single chokepoint
  routes/
    config.py              # GET/POST /api/config, GET /api/configs
    export.py              # POST /api/export -> print_render.py
    schema.py              # GET /api/schema  -> enums, defaults
  tests/
    test_config_roundtrip.py
    test_export.py
    test_curves_parity.py  # cross-check curves.ts vs curves.py
  static/                  # vite build output (gitignored except .gitkeep)
  web/                     # Svelte source (Vite project)
    src/
      lib/{api,curves,store,types}.ts
      components/
        ActionLibrary.svelte
        ActionInspector.svelte
        ControllerView.svelte
        CurveEditor.svelte
        LivePreview.svelte
        BindingMenu.svelte
      routes/+page.svelte
      assets/
        xbox-controller.svg     # from images/Xbox_Controller.svg
        xbox-hitboxes.json      # hit regions keyed by input name
    package.json
    vite.config.ts
```

### Why these choices

- **Svelte + TypeScript + Vite.** Smallest learning curve for a Python-first contributor — components look close to HTML, reactive variables behave like attributes. Bundle is small enough to load on the field network.
- **2D SVG with a JSON hit-region overlay.** Decouples hit regions from artwork so swapping the SVG (or adding a 3D view later) doesn't disturb the binding logic.
- **Server-side PNG/PDF export** via existing [print_render.py](../controller_config/print_render.py). Printed output stays byte-stable with the current tool — no parallel print layout to maintain.
- **Path allowlist under `data/`** via `paths.py`. Path widening is a one-line change later.

### Data flow

1. Frontend never parses YAML. Server round-trips JSON of `FullConfig`.
2. Curve math: port [utils/math/curves.py](../../utils/math/curves.py) → `curves.ts`. `test_curves_parity.py` pins identical output for a fixed input grid.
3. Edits live in an in-memory store with undo. Explicit Save → POST → `config_io.save_config()`.
4. Export: POST current in-memory state to `/api/export`; server renders via `print_render.py`; returns the file.

## Migration phases

1. Scaffold + `/api/config` round-trip. Raw JSON in browser proves the loop.
2. Action CRUD + menu binding (reqs 1, 2, 3, 6).
3. SVG controller + drag-to-bind via hitbox overlay (req 4).
4. Curve editor + live preview, port `curves.ts`, gamepad input (req 5).
5. Export endpoint wired to `print_render.py` (req 8).
6. Polish — keyboard shortcuts, deep links, a11y.
7. Ship alongside Tkinter for one release, then deprecate.

## Risks

- Curve math drift between Python and TS — mitigated by `test_curves_parity.py`.
- Hit-region authoring for [images/Xbox_Controller.svg](../../images/Xbox_Controller.svg) — one-time effort, lives in `web/src/assets/xbox-hitboxes.json`.
- Browser preview won't be pixel-identical to server-rendered print. Acceptable tradeoff.
