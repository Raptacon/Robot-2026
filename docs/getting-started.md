# Getting Started

This guide gets you from zero to a working development environment. By the end you'll be able to run the robot simulator and run the test suite on your laptop — no robot required.

---

## Prerequisites

### 1. Python

RobotPy requires a specific Python version. For the 2026 season, install **Python 3.13** from [python.org](https://www.python.org/downloads/).

> **All users:** We recommend [pipenv](https://pipenv.pypa.io/) to manage Python versions and virtual environments. It keeps your project dependencies isolated and makes switching between Python versions straightforward. Install it with `pip install pipenv` after installing Python.

Check your version:
```bash
python3 --version
# Should show Python 3.13.x
```

### 2. Git

[Download Git](https://git-scm.com/downloads) if you don't have it. On macOS, running `git` in a terminal will prompt you to install it.

> **Windows users:** Download [Git for Windows](https://git-scm.com/download/win) — it includes **Git Bash**, a terminal that lets you use the same commands as macOS and Linux. Use Git Bash for all the commands in this guide. See the team [developer-tools repo](https://github.com/Raptacon/developer-tools) for a Windows setup script that automates most of this.

### 3. VS Code (recommended)

[Download VS Code](https://code.visualstudio.com/). Install these extensions:
- **Python** (by Microsoft) — syntax highlighting, autocomplete
- **Pylance** — better Python type checking
- **Markdown Preview Mermaid Support** — renders our architecture diagrams in previews

---

## Clone the Repository

```bash
git clone https://github.com/Raptacon/Robot-2026.git
cd Robot-2026
```

---

## Install Dependencies

We use a `Makefile` to automate setup. Running any `make` target (like `make sim` or `make test`) will automatically create the virtual environment and install dependencies on first run:

```bash
# macOS/Linux:
make sim       # sets up the environment, then launches the simulator
make test      # sets up the environment, then runs tests

# Windows (Git Bash):
make sim
make test
```

The Makefile creates a platform-specific virtual environment automatically:
- macOS: `.venv_osx/`
- Windows: `.venv_windows/`

> **Windows users:** You need `make` installed. The easiest way is [Chocolatey](https://chocolatey.org/):
> ```powershell
> # Run PowerShell as Administrator, then:
> Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
> choco install make
> ```
> Or use the setup script in the [developer-tools repo](https://github.com/Raptacon/developer-tools).

### Manual setup (if `make` doesn't work)

```bash
# macOS/Linux:
python3 -m venv .venv_osx
source .venv_osx/bin/activate

# Windows (Git Bash):
python -m venv .venv_windows
source .venv_windows/Scripts/activate

pip install -r requirements.txt
python -m robotpy sync
```

---

## Activate the Virtual Environment

Every time you open a new terminal, you need to activate the virtual environment:

```bash
# macOS/Linux:
source .venv_osx/bin/activate

# Windows (Git Bash):
source .venv_windows/Scripts/activate
```

VS Code can do this automatically — open the Command Palette (`Ctrl+Shift+P`), type "Python: Select Interpreter", and pick the one inside `.venv_osx/` or `.venv_windows/`.

---

## Run the Simulator

The simulator lets you run the robot code without any hardware:

```bash
# Using make (runs tests first, then launches sim)
make sim

# Direct Python (launches sim immediately, no test run)
python -m robotpy sim
```

A window will open showing the simulated robot's state. You can:
- Enable/disable the robot (like the real Driver Station)
- Switch between Autonomous and Teleop modes
- Connect a real Xbox controller or use the keyboard

> **What you should see:** The simulator window opens, you can enable the robot, and switch modes without any errors in the terminal.

---

## Run the Tests

Tests verify the robot code works correctly without needing a real robot:

```bash
# Run all tests (direct Python command)
python -m robotpy test

# Run with coverage (shows which lines were tested)
python -m robotpy coverage test

# Run a specific test file
python -m robotpy test -- tests/test_intake.py -v

# Run a specific test by name
python -m robotpy test -- tests/test_fuzz_teleop.py::test_fuzz_teleop_short -v
```

> **Note:** The `--` separator is required when passing arguments to pytest through the robotpy test runner. Everything after `--` goes to pytest.

> **What you should see:** All tests pass with no errors. If something fails, check the error message — it usually tells you exactly what's wrong.

Tests run automatically every time you push code to GitHub (CI), and also when you deploy to the robot (`make deploy`). If tests fail, the code won't deploy.

---

## Run the Controller Config GUI

We have a visual tool for configuring Xbox controller button mappings:

```bash
# Install GUI-only dependencies (first time only)
pip install -r host/requirements.txt

# Launch the GUI
python -m host.controller_config
```

See [host/controller_config/ARCHITECTURE.md](../host/controller_config/ARCHITECTURE.md) for details.

---

## Project Structure

Here's a map of the important files and folders:

```
Robot-2026/
├── robot.py                    # Entry point — WPILib starts here
├── robotswerve.py              # Robot container — wires everything together
├── constants/                  # Physical hardware constants (gear ratios, etc.)
├── config.py                   # Operator-tunable settings (PID gains, etc.)
├── subsystem/                  # Hardware subsystems (drivetrain, intake, etc.)
│   ├── __init__.py             # Imports that trigger subsystem registration
│   ├── manifest.py             # Which subsystems run on which robot
│   ├── drivetrain/             # Swerve drive code
│   └── mechanisms/             # Other mechanisms (turret, etc.)
├── commands/                   # Commands and controller bindings
│   └── *_controls.py          # One file per subsystem, wires buttons → commands
├── utils/                      # Shared utilities
│   ├── subsystem_factory.py    # Registry/factory pattern (core architecture)
│   ├── loop_timing.py          # Loop performance monitoring
│   └── input/                  # Controller input management
├── tests/                      # All automated tests
├── data/                       # Config files (controller YAML, etc.)
├── docs/                       # You are here
└── host/                       # Desktop tools (controller config GUI)
```

---

## Deploying to the Robot

When you're connected to the robot's WiFi:

```bash
make deploy
# OR:
python -m robotpy deploy
```

This will:
1. Run all tests — deployment stops if any test fails
2. Sync library packages to the robot if needed
3. Copy your code to the robot

> **Important:** You need to be connected to the robot's WiFi network, and the robot must be powered on.

---

## Common Problems

### `ModuleNotFoundError: No module named 'wpilib'`
You're not in the virtual environment. Run `source .venv_osx/bin/activate` (macOS) or `source .venv_windows/Scripts/activate` (Windows Git Bash).

### Simulator opens but immediately crashes
Check the terminal for a Python traceback. Usually a syntax error in your code or a missing import.

### `python -m robotpy sync` fails
Check your internet connection. The sync command downloads WPILib simulation files.

### Tests fail with `NoneType` errors
A subsystem that should exist is `None`. Check that it's imported in `subsystem/__init__.py` and that its `register_subsystem()` call is at the bottom of its file.

---

## Next Steps

Now that your environment is working, read the [Architecture Overview](architecture/README.md) to understand how the robot code is structured.

If you want to practice FRC programming concepts before diving into this codebase, check out the [Skills Challenges](https://github.com/Raptacon/Skills-Challenges) repository — it has step-by-step exercises designed for exactly this.
