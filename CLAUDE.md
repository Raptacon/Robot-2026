# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FRC Team 3200 (Raptacon) robot code for the 2026 season. Written in Python using RobotPy (WPILib's Python bindings) with the Commands2 framework. The robot runs a 4-module MK4i swerve drivetrain with SparkMax motor controllers (REV NEO motors) and CTRE CANcoders.
Note that wpilib is avaiable in C++, Java and python. Most resources are listed as C++ or java but almost all code transfers to python with minor updates to match python nuances and style.

## Build & Development Commands

**Setup (first time):**
```bash
make                    # Creates venv and installs dependencies (uses Makefile)
# OR manually:
python -m venv venv
pip install -r requirements.txt
python -m robotpy sync  # Installs pyproject.toml dependencies to robotpy cache
```

**Run simulator:**
```bash
make sim                # Runs coverage tests then launches simulator
python -m robotpy sim   # Direct simulator launch
```

**Run tests:**
```bash
python -m robotpy test              # Run all tests
python -m robotpy coverage test     # Run tests with coverage (used by CI)
```

**Lint:**
```bash
make lint
# Or directly:
flake8 . --count --select=E9,F6,F7,F8,F4,W1,W2,W4,W5,W6,E11 --ignore W293,W503 --show-source --statistics --exclude */tests/pyfrc*,utils/yaml/*,.venv*/,venv*/,examples/robotpy/*
```

**Deploy to robot:**
```bash
make deploy             # Deploys libraries and code to the robot. (requires robot connection)
python -m robotpy deploy
```

**Run controller config GUI:**
```bash
pip install -r host/requirements.txt   # First time only (Pillow, PyYAML)
python -m host.controller_config       # Launch GUI
```

**Style:**
Follow major style guidelines from PEP8 based on what is configured for flake8.

## Architecture

### Entry Point & Robot Lifecycle

`robot.py` defines `MyRobot(commands2.TimedCommandRobot)` running at 20 Hz (50ms period). It delegates all logic to `RobotSwerve` (in `robotswerve.py`), which acts as the **robot container** - it builds a manifest, creates a `SubsystemRegistry`, and exposes convenience accessors. Subsystem creation, telemetry, and controls are handled by the registry via convention-based discovery (see Subsystem Registry below).

`MyRobot.__callAndCatch` wraps periodic calls to catch and log exceptions without crashing the robot on hardware (exceptions are re-raised in simulation).

### Configuration Separation

- **`constants.py`** - Physical hardware constants (robot dimensions, gear ratios, conversion factors, current limits). Uses class inheritance: `RobotConstants` -> `SwerveDriveConsts` -> `SwerveModuleMk4iConsts` -> `SwerveModuleMk4iL2Consts`
- **`config.py`** - Operator-tunable parameters (`OperatorRobotConfig`): PID gains, encoder calibrations, vision thresholds, CAN channel assignments, PathPlanner constraints, default start poses

### Subsystem Registry (`utils/subsystem_factory.py`)

Subsystems are **self-contained and self-registering**. Each subsystem module calls `register_subsystem()` at the bottom of its file. Importing `subsystem` (via `subsystem/__init__.py`) triggers all registrations.

**Key types:**
- `SubsystemEntry` — declares name, default state, creator function, and dependencies
- `SubsystemFactory` — creates a single subsystem with error isolation (required subsystems raise on failure, enabled ones degrade gracefully)
- `SubsystemRegistry` — processes a manifest of entries: resolves NT-persisted state, checks dependencies, creates subsystems, and provides convention-based lifecycle methods

**Convention-based lifecycle:**
- **Controls**: auto-discovers `commands/{name}_controls.py` and calls `register_controls(subsystem, container)`
- **Telemetry**: calls `subsystem.updateTelemetry()` if the method exists
- **Disabled init**: calls `subsystem.onDisabledInit()` if the method exists

**Robot manifests** (`subsystem/manifest.py`): `ROBOT_MANIFESTS` maps robot name strings to manifest builders. Entries are topologically sorted (Kahn's algorithm) so dependencies are created first. Available manifests:
- `"competition"` — all registered subsystems
- `"sparky"` — drivetrain only
- `None` — fallback, defaults to competition

The active robot name is persisted via `ntproperty` at `/robot/name`.

**Adding a new subsystem:**
1. Create subsystem class in `subsystem/` with optional `updateTelemetry()` and `onDisabledInit()` methods
2. Add `register_subsystem()` call at bottom of module
3. Add one import line in `subsystem/__init__.py`
4. Optionally create `commands/{name}_controls.py` with `register_controls(subsystem, container)`

No manifest editing or `robotswerve.py` changes needed.

### Subsystems (`subsystem/`)
Subsystems contain code to control or logically group mechanisms and software components on the robot. Subsystems directly control hardware through the wpilib library.
- **`drivetrain/`** : Contains code for the drivetrain of the robot
- **`drivetrain/swerve_drivetrain.py`** - `SwerveDrivetrain(Subsystem)`: manages 4 swerve modules, gyroscope (NavX), pose estimation (SwerveDrive4PoseEstimator), PathPlanner integration, field-relative drive. Owns a `Field2d` for dashboard visualization. Uses "always blue" coordinate system.
- **`drivetrain/swerve_module.py`** - `SwerveModuleMk4iSparkMaxNeoCanCoder`: individual module with drive motor, steer motor (both SparkMax/NEO via REV), and absolute encoder (CANcoder via Phoenix6). CAN IDs use consecutive numbering: base=drive, base+1=steer, base+2=encoder.
- **`localization/`** : Contains code pertaining to locating the robot physically on the field of play and determining correct goals based on red or blue alliance teams.
- **`mechanisms/`** : Contains robot mechanisms such as turrets, flywheel shooters, intakes, hoppers and climbers.

### Commands (`commands/`)
The command folder contains the commands which act on subsystems. Groups of commands can be used to accomplish more complex tasks. Default commands run whenever another command
does not currently require a subsystem and are used for default behaviors or passing driver controls to subsystems.
- **`{name}_controls.py`** - Convention-based control files auto-discovered by the registry. Each exports `register_controls(subsystem, container)` to wire HID bindings and default commands.
- **`default_swerve_drive.py`** - `DefaultDrive`: teleop Xbox controller driving (left stick translate, right stick rotate)
- **`autoDrive.py`** - `AutoDrive`: time-based autonomous drive
- **`auto/pid_to_pose.py`** - `PIDToPose`: profiled PID alignment to target pose
- **`auto/pathplan_to_pose.py`** - `pathplanToPose()`: PathPlanner-based pathfinding to target pose (avoids field obstacles via navgrid)
- **`auto/pathplan_to_path.py`** - PathPlanner path following

### Examples (`examples/`)
This directory contains examples and allows a location to develop new robots.py for limited hardware environments. We will create a new folder for each example robot.py that we may test with which will follow the same structure as the base directory.
- **`robotpy`** : Contains a set of wpilib examples that show how to do certain tasks with the wpilib library.
- **`flywheel-sysid`** : Contains a example of how to collect data to run sysid on various mechanical components.

### Telemetry (`data/telemetry.py`)

Logs controller inputs, odometry, swerve module states, and driver station data via NetworkTables and WPILib DataLog. Per-subsystem telemetry is handled by each subsystem's own `updateTelemetry()` method, called automatically by the registry.

### PathPlanner Integration

Autonomous routines are defined as `.auto` and `.path` files in `deploy/pathplanner/`. PathPlanner is configured in `SwerveDrivetrain.configure_path_planner()` via `AutoBuilder`. The auto chooser is exposed on SmartDashboard.

### Controller Config Model (`utils/controller/`)

Shared pure-Python data model used by both the GUI tool and robot code. No wpilib dependency.

- **`model.py`** - `ActionDefinition` (name, description, input_type, trigger_mode, deadband, inversion, scale, extra), `ControllerConfig` (port, name, bindings), `FullConfig` (actions + controllers). Enums: `InputType` (BUTTON/AXIS/POV/OUTPUT), `TriggerMode` (ON_TRUE/ON_FALSE/WHILE_TRUE/WHILE_FALSE/TOGGLE_ON_TRUE/RAW).
- **`config_io.py`** - `load_config(path)` / `save_config(config, path)` for YAML serialization. Omits default values for clean output.
- Config files stored in `data/controller.yaml`

**Robot-side integration (not yet implemented):**
To use GUI-configured bindings on the robot, a future `commands/controller_loader.py` would:
1. Call `load_config("data/controller.yaml")` at robot init
2. For each controller port, create `commands2.button.CommandXboxController(port)`
3. Map each binding entry to the appropriate trigger (e.g., `controller.a()` for `a_button`, `controller.leftTrigger()` for `left_trigger`)
4. Apply `TriggerMode` to determine wpilib trigger method (`.onTrue()`, `.whileTrue()`, `.toggleOnTrue()`, etc.)
5. Wire to the command referenced by the action name

### Controller Config GUI (`host/controller_config/`)

Host-side tkinter tool for visually mapping Xbox controller inputs to robot actions. Run with `python -m host.controller_config`. Requires `pip install -r host/requirements.txt` (Pillow, PyYAML).

**Key files:**
- **`app.py`** - Main `ControllerConfigApp(tk.Tk)` window: menu bar, tabbed controllers, action panel, status bar. Orchestrates callbacks between canvas and data model.
- **`controller_canvas.py`** - `ControllerCanvas(tk.Frame)`: renders Xbox controller image with interactive binding boxes, leader lines, clickable button shapes, rumble icons, drag support, hover highlighting, and tooltips.
- **`layout_coords.py`** - Defines all input positions (`InputCoord`) and clickable shapes (`ButtonShape`) in fractional coordinates (0-1) relative to a 1920x1292 source image. Helper functions `_fx()`/`_fy()` convert pixel coords to fractions.
- **`action_panel.py`** - `ActionPanel(tk.Frame)`: CRUD for `ActionDefinition` objects (name, description, input type, trigger mode, deadband, inversion, scale).
- **`binding_dialog.py`** - `BindingDialog`: modal dialog for assigning actions to a controller input.
- **`main.py`** - CLI entry point with argparse.

**Design patterns:**
- Canvas uses callback-based architecture — parent (app.py) passes `on_binding_click`, `on_hover_input`, `on_hover_shape`, etc.
- Label positions are draggable and persist to `.settings.json` (gitignored)
- Shape borders hidden by default, toggleable via View menu
- PIL `ImageDraw` fallback for rumble icon when `cairosvg` unavailable (common on Windows)

### CAN ID Convention

Drivetrain modules start at CAN ID 50 with 3 consecutive IDs per module (drive, steer, encoder). Additional mechanisms count backwards from CAN ID 40. See `subsystem/CAN_CONFIG.md`.

## Key Libraries

- `robotpy` 2026.x - WPILib Python bindings
- `robotpy-rev` - REV SparkMax motor controllers
- `phoenix6` - CTRE CANcoder absolute encoders
- `robotpy-navx` - NavX gyroscope
- `robotpy-pathplannerlib` - Autonomous path planning
- `photonlibpy` - PhotonVision camera integration
- `commands2` - WPILib command-based framework
- `robotpy-urcl` - Unoffical library to enable capture of Rev Robotics CAN control frames.

## CI Pipeline

GitHub Actions (`.github/workflows/robot_ci.yml`) runs on Windows:
- Unit tests: `python -m robotpy coverage test`
- Lint (critical): flake8 with select rules for syntax errors and undefined names
- Lint (extra): flake8 with complexity and line-length checks (non-blocking)
- Docstring verification (non-blocking)


## Unit Tests
 - Unit tests should be encouraged and written
 - Unit tests generated by Claude should be commented as such
 - Unit tests should use sim feedback when working with hardware based devices
 - Prefer pytest style (plain classes + `assert`) over `unittest.TestCase` — pyfrc/robotpy uses pytest as its test runner

## NetworkTables Persistence

Use `ntcore.util.ntproperty` for values that need to persist across reboots (calibration data, saved positions, etc.). Declare as class-level attributes with `persistent=True` and `writeDefault=False` so existing persisted values are not overwritten on startup:

```python
from ntcore.util import ntproperty

class MySubsystem:
    saved_limit = ntproperty('/MySubsystem/saved_limit', 0.0,
                             writeDefault=False, persistent=True)
```

See `examples/nt-persistence-test/` for a comparison of persistence approaches.

## Commit messages
 - Leave off Claude coauthor for main files

## Claude.md updates
If Claude sees an area that would benifit for remembering or having instructions in the future Claude should suggest adding it to CLAUDE.md

