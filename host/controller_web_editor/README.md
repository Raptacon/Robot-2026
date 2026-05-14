# Controller Web Editor

Web-app replacement for the Tkinter tool in [../controller_config](../controller_config).
Edits the same YAML files under `data/inputs/` and produces the same
printable PNG/PDF output via the shared `print_render.py` pipeline.

See [CLAUDE.md](CLAUDE.md) for the architecture and design notes.

## Quick start (just running it)

The compiled SPA is committed under [static/](static), so a fresh checkout
runs without Node.  From the repo root:

**Windows (PowerShell):**
```powershell
.\scripts\controller_editor\launch.ps1
```

**macOS / Linux:**
```bash
./scripts/controller_editor/launch.sh
```

The script creates `venv/` if missing, installs deps the first time
(skipped on subsequent runs unless the requirements files change), then
launches the server and opens <http://127.0.0.1:8071> in your browser.

If you'd rather do it by hand:

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
pip install -r host/requirements.txt

python -m host.controller_web_editor
```

### Common flags

```bash
python -m host.controller_web_editor --host 0.0.0.0 --port 8071
```

`--host 0.0.0.0` lets other machines on the LAN connect.

## Developer workflow (editing the SPA)

If you change anything under `web/src/`, the server rebuilds the bundle
automatically on the next start when it detects newer mtimes than
`static/`.  This needs Node.js installed (LTS works) — get it from
<https://nodejs.org>.

For interactive development with hot reload, run the Vite dev server in
a second terminal:

```bash
cd host/controller_web_editor/web
npm install      # first time only
npm run dev      # serves SPA on http://127.0.0.1:5173 with HMR
```

In another terminal run the Python server as usual (`python -m host.controller_web_editor`).
Vite proxies `/api/*` to port 8071 — see `vite.config.ts`.

To rebuild the committed bundle manually:

```bash
cd host/controller_web_editor/web
npm run build
```

`npm run check` runs `svelte-check` (TypeScript + Svelte diagnostics).

### Skipping the auto-build

Set `CONTROLLER_WEB_EDITOR_SKIP_BUILD=1` in the environment if you want
to short-circuit the build step (e.g., CI that pre-builds the bundle as
part of an artifact stage).

## Headless export (for CI / docs)

The same renderer powers a GET endpoint and the Tkinter tool's CLI.
Either works for pipelines.

**HTTP** (works while the server is running):

```bash
curl -fsSO \
  "http://127.0.0.1:8071/api/export?path=data/inputs/controller.yaml&orientation=landscape&format=pdf&hide_unassigned=1"
```

**CLI** (no server needed; same renderer):

```bash
python -m host.controller_config data/inputs/controller.yaml \
  --export build/controller.pdf --orientation landscape
```

PNG output is single-page only — use PDF for multi-controller layouts.

### GitHub Actions deps

- `cairosvg` needs `libcairo`.  On `ubuntu-latest`:
  `sudo apt-get install -y libcairo2 fonts-dejavu-core`.
- A pre-rendered `images/Xbox_Controller.svg.png` is the cairosvg
  fallback — commit one to skip the Cairo dependency entirely.

## Running the tests

```bash
venv/Scripts/python.exe -m pytest host/controller_web_editor/tests/ -q
```

Tests cover the JSON ↔ YAML round-trip, hitbox layout I/O, curves
parity with the Python implementation, and export endpoint wiring.

## Troubleshooting

- **Browser shows "The SPA isn't built yet" page** — the committed bundle
  is missing.  Run `cd web && npm install && npm run build`.  If Node
  isn't available, pull a fresh checkout; the bundle is tracked in git.
- **`pip install -r host/requirements.txt` fails on `cairosvg`** —
  cairosvg needs the Cairo C library.  See the GHA section above for
  the apt/brew packages.  Alternatively, drop a pre-rendered
  `images/Xbox_Controller.svg.png` and skip cairosvg entirely.
- **Export button is disabled** — either no config is loaded, or the
  current config has unsaved changes.  The endpoint reads YAML from
  disk, so save first.
- **Port 8071 already in use** — pass `--port 8072` (or any free port).

## File layout

```
host/controller_web_editor/
  __main__.py            # python -m entry point
  serve.py               # HTTP server, static + /api/* routes
  build.py               # auto-build helper (mtime-aware npm run build)
  paths.py               # safe_resolve() allowlist for data/
  routes/
    config.py            # /api/config, /api/configs
    export.py            # /api/export -> print_render.render_to_bytes
    hitboxes.py          # /api/hitboxes
  hitboxes/xbox.json     # SVG hit-region overlay (per controller type)
  static/                # built SPA (committed)
  web/                   # Svelte 5 + TS + Vite source
    src/lib/             # api/store/curves/types
    src/components/      # ActionLibrary, ActionInspector,
                         # ControllerView, BindingMenu,
                         # CurveEditor, LivePreview, ExportMenu
  tests/                 # pytest, no GUI
```
