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
flake8 . --count --select=E9,F6,F7,F8,F4,W1,W2,W4,W5,W6,E11 --ignore W293,W503 --show-source --statistics --exclude */tests/pyfrc*,utils/yaml/*,.venv*/,venv*/
```

**Deploy to robot:**
```bash
make deploy             # Deploys libraries and code to the robot. (requires robot connection)
python -m robotpy deploy
```

**Style:**
Follow major style guidelines from PEP8 based on what is configured for flake8.

## Architecture

### Entry Point & Robot Lifecycle

`robot.py` defines `MyRobot(commands2.TimedCommandRobot)` running at 20 Hz (50ms period). It delegates all logic to `RobotSwerve` (in `robotswerve.py`), which acts as the **robot container** - it instantiates all subsystems, configures controls, sets up autonomous, and manages telemetry.

`MyRobot.__callAndCatch` wraps periodic calls to catch and log exceptions without crashing the robot on hardware (exceptions are re-raised in simulation).

### Configuration Separation

- **`constants.py`** - Physical hardware constants (robot dimensions, gear ratios, conversion factors, current limits). Uses class inheritance: `RobotConstants` -> `SwerveDriveConsts` -> `SwerveModuleMk4iConsts` -> `SwerveModuleMk4iL2Consts`
- **`config.py`** - Operator-tunable parameters (`OperatorRobotConfig`): PID gains, encoder calibrations, vision thresholds, CAN channel assignments, PathPlanner constraints, default start poses

### Subsystems (`subsystem/`)
Subsystems contain code to control or logically group mechanisms and software components on the robot. Subsystems directly control hardware through the wpilib library.
- **`drivertrain` : Contains code for the drivetrain of the robot
- **`drivetrain/swerve_drivetrain.py`** - `SwerveDrivetrain(Subsystem)`: manages 4 swerve modules, gyroscope (NavX), pose estimation (SwerveDrive4PoseEstimator), PathPlanner integration, field-relative drive. Uses "always blue" coordinate system.
- **`drivetrain/swerve_module.py`** - `SwerveModuleMk4iSparkMaxNeoCanCoder`: individual module with drive motor, steer motor (both SparkMax/NEO via REV), and absolute encoder (CANcoder via Phoenix6). CAN IDs use consecutive numbering: base=drive, base+1=steer, base+2=encoder.
- **`localization` : Contains code pertaining to locating the robot physically on the field of play and determining correct goals based on red or blue alliance teams.
- **`mechanisms` : Contains robot mechanisms such as flywheel shooters, intakes, hoppers and climbers.

### Commands (`commands/`)
The command folder contains the commands which act on subsystems. Groups of commands can be used to accomplish more complex tasks. Default commands run whenever another command
does not currently require a subsystem and are used for default behaviors or passing driver controls to subsystems. 
- **`default_swerve_drive.py`** - `DefaultDrive`: teleop Xbox controller driving (left stick translate, right stick rotate)
- **`autoDrive.py`** - `AutoDrive`: time-based autonomous drive
- **`auto/pid_to_pose.py`** - `PIDToPose`: profiled PID alignment to target pose
- **`auto/pathplan_to_pose.py`** - `pathplanToPose()`: PathPlanner-based pathfinding to target pose (avoids field obstacles via navgrid)
- **`auto/pathplan_to_path.py`** - PathPlanner path following

### Examples (`examples/`)
This directory contains examples and allows a location to develop new robots.py for limited hardware environments. We will create a new folder for each example robot.py that we may test with which will follow the same structure as the base directory.
- **`robotpy`** : Contains a set of wpilib examples that show how to do certain tasks with the wpilib library.
- **`flywheel-sysid`** : Contains a example of how to collect data to run sysid on various mechanical components.

### Vision (`vision.py`)

Uses PhotonVision with two cameras. Filters AprilTag detections by ambiguity and distance thresholds, then feeds pose estimates into the drivetrain's `SwerveDrive4PoseEstimator` with distance-scaled standard deviations.

### Telemetry (`data/telemetry.py`)

Logs controller inputs, odometry, swerve module states, vision estimates, and driver station data via NetworkTables and WPILib DataLog.

### PathPlanner Integration

Autonomous routines are defined as `.auto` and `.path` files in `deploy/pathplanner/`. PathPlanner is configured in `SwerveDrivetrain.configure_path_planner()` via `AutoBuilder`. The auto chooser is exposed on SmartDashboard.

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
