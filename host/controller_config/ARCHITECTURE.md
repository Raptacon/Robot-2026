# Controller Config - Detailed Architecture

Reference doc for Claude Code when working on the controller configuration system.

## Data Model (`utils/controller/`)

Shared pure-Python data model used by both the GUI tool and robot code. No wpilib dependency.

### `model.py` - Core Dataclasses and Enums

- `ActionDefinition` — name, description, group, input_type, trigger_mode, deadband, inversion, scale, extra. Qualified name is `group.name` (e.g. `intake.run`).
- `ControllerConfig` — port, name, controller_type, bindings (dict mapping input names to lists of action qualified names)
- `FullConfig` — actions (dict[str, ActionDefinition]) + controllers (dict[int, ControllerConfig])
- `InputType` enum: BUTTON, ANALOG, POV, OUTPUT
- `EventTriggerMode` enum: button modes (ON_TRUE, ON_FALSE, WHILE_TRUE, WHILE_FALSE, TOGGLE_ON_TRUE) and analog response curves (RAW, SCALED, SQUARED, SEGMENTED, SPLINE)
- `BUTTON_EVENT_TRIGGER_MODES` / `ANALOG_EVENT_TRIGGER_MODES` — lists filtering which trigger modes apply to each input type

### `config_io.py` - YAML Serialization

- `load_config(path)` / `save_config(config, path)` — full config round-trip
- `load_actions_from_file()` / `save_actions_to_file()` — actions-only import/export
- `load_assignments_from_file()` / `save_assignments_to_file()` — controllers-only import/export
- Auto-detects nested (grouped) vs flat (legacy) action format
- Migrates old `"axis"` input type to `"analog"`, upgrades bare binding names to qualified names
- Omits default values for clean YAML output

### Action Naming Convention

Actions use qualified names in the format `group.name` (e.g. `intake.run`, `shooter.fire`, `general.reset_gyro`). Actions without an explicit group default to `"general"`. The `FullConfig.actions` dict and all controller bindings are keyed by qualified name. YAML format stores actions nested by group:

```yaml
actions:
  intake:
    run:
      description: Run intake motor
      input_type: button
  drivetrain:
    field_orient:
      description: Toggle field-oriented drive
      input_type: button
      trigger_mode: toggle_on_true
controllers:
  0:
    name: Driver
    bindings:
      a_button: [intake.run]
      b_button: [drivetrain.field_orient]
```

Config files stored in `data/controller.yaml`.

### Robot-Side Integration (not yet implemented)

To use GUI-configured bindings on the robot, a future `commands/controller_loader.py` would:
1. Call `load_config("data/controller.yaml")` at robot init
2. For each controller port, create `commands2.button.CommandXboxController(port)`
3. Map each binding entry to the appropriate trigger (e.g., `controller.a()` for `a_button`, `controller.leftTrigger()` for `left_trigger`)
4. Apply `EventTriggerMode` to determine wpilib trigger method (`.onTrue()`, `.whileTrue()`, `.toggleOnTrue()`, etc.)
5. Look up the command by the qualified action name (e.g. `intake.run` -> `IntakeSubsystem.run_command()`)

## GUI Tool (`host/controller_config/`)

Host-side tkinter app for visually mapping Xbox controller inputs to robot actions. Run with `python -m host.controller_config [config.yaml]`. Requires Pillow and PyYAML (in `requirements.txt`).

### Key Files

- **`app.py`** - Main `ControllerConfigApp(tk.Tk)` window: menu bar, tabbed controllers, action panel, status bar. Orchestrates drag-and-drop, undo/redo, import/export, and callbacks between canvas and data model. Module-level `load_settings()` for CLI use.
- **`controller_canvas.py`** - `ControllerCanvas(tk.Frame)`: renders Xbox controller image with interactive binding boxes, leader lines, clickable button shapes, rumble icons, drag-and-drop with type compatibility overlays (green borders on compatible, grey dimming on incompatible), hover highlighting, and tooltips.
- **`layout_coords.py`** - Defines all input positions (`InputCoord`) and clickable shapes (`ButtonShape`) in fractional coordinates (0-1) relative to a 1920x1292 source image. Helper functions `_fx()`/`_fy()` convert pixel coords to fractions.
- **`action_panel.py`** - `ActionPanel(tk.Frame)`: CRUD for `ActionDefinition` objects (name, description, group, input type, trigger mode, deadband, inversion, scale). Supports drag initiation for drag-and-drop binding. Uses `_updating_form` guard to prevent cascading trace callbacks during undo/input type changes.
- **`binding_dialog.py`** - `BindingDialog`: modal dialog for assigning actions to a controller input.
- **`import_dialog.py`** - `ImportDialog`: modal for importing/merging actions or assignments from external YAML files.
- **`print_render.py`** - Off-screen PIL renderer for PNG/PDF export. Mirrors canvas visuals using `ImageDraw`. Supports portrait (2 controllers/page) and landscape (1/page) at 150 DPI letter size. PDF via Pillow native `Image.save("file.pdf", save_all=True)` — no extra deps.
- **`main.py`** - CLI entry point with argparse. Supports `--export OUTPUT` for headless PNG/PDF export, `--orientation`, `--hide-unassigned`.

### Design Patterns

- Canvas uses callback-based architecture — parent (app.py) passes `on_binding_click`, `on_hover_input`, `on_hover_shape`, etc.
- Label positions are draggable and persist to `.settings.json` (gitignored)
- Shape borders hidden by default, toggleable via View menu
- View > Hide Unassigned Inputs toggle applies to canvas and export; temporarily disabled during drag-and-drop
- Drag-and-drop shows type compatibility: green borders on compatible inputs/shapes, grey stipple overlay on incompatible
- Undo/redo with snapshot coalescing for rapid text edits
- PIL `ImageDraw` fallback for rumble icon when `cairosvg` unavailable (common on Windows)

### Printing and Exporting

#### From the GUI

1. Open a config: `python -m host.controller_config data/controller.yaml`
2. File > Print / Export > choose format and orientation:
   - **Portrait (2 per page) - PNG** — two controllers stacked on a letter page
   - **Portrait (2 per page) - PDF** — same as above, multi-page PDF if >2 controllers
   - **Landscape (1 per page) - PNG** — one controller per page, wider layout
   - **Landscape (1 per page) - PDF** — same as above, multi-page PDF
3. Choose save location in the file dialog
4. To hide unbound inputs: View > Hide Unassigned Inputs (checked state carries into export)

#### From the Command Line (no GUI)

Export directly without opening the GUI — useful for CI pipelines and documentation builds.

```bash
# PDF, landscape, one controller per page
python -m host.controller_config data/controller.yaml --export docs/controllers.pdf --orientation landscape

# PNG, portrait, two controllers per page
python -m host.controller_config data/controller.yaml --export docs/controllers.png

# Hide inputs that have no bindings
python -m host.controller_config data/controller.yaml --export docs/controllers.pdf --hide-unassigned

# Combine options
python -m host.controller_config data/controller.yaml --export docs/controllers.png --orientation landscape --hide-unassigned
```

**CLI arguments:**
| Argument | Description |
|----------|-------------|
| `config_file` | Path to YAML config (required for export) |
| `--export OUTPUT` | Output file path (.png or .pdf) |
| `--orientation` | `portrait` (default, 2/page) or `landscape` (1/page) |
| `--hide-unassigned` | Omit inputs with no bindings |

**Output details:**
- Resolution: 150 DPI, US Letter size (8.5 x 11 inches)
- PNG multi-page: appends `_page1`, `_page2` suffixes to filename
- PDF multi-page: single file with all pages
- PDF generation uses Pillow natively — no extra dependencies
