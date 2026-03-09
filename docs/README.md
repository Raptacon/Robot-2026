# Raptacon Robot 2026 — Documentation

Welcome to the team documentation for FRC Team 3200 (Raptacon) Robot 2026.

Whether you're setting up your laptop for the first time or trying to understand how the robot's software is structured, you're in the right place.

---

## Where to Start

### New to the team? Start here:
**[Getting Started](getting-started.md)** — Install everything, run the simulator, run tests. Get your environment working before you touch any robot code.

### Ready to learn how the code works?
**[Architecture Overview](architecture/README.md)** — The big picture. How does a robot program actually run? What are all these files? Start here before diving into any individual topic.

---

## Documentation Index

| Document | What it covers |
|---|---|
| [Getting Started](getting-started.md) | Installation, setup, running the sim, running tests |
| [Architecture Overview](architecture/README.md) | High-level structure, robot lifecycle, how everything connects |
| [Commands V2](architecture/commands-v2.md) | The most important concept in FRC programming — deep dive with state machine theory |
| [Subsystem Registry](architecture/subsystem-registry.md) | How our robot creates and manages hardware components safely |
| [Adding a Subsystem](architecture/adding-a-subsystem.md) | Step-by-step guide: add a new mechanism to the robot |
| [Testing](architecture/testing.md) | How to write and run tests, pyfrc simulation, CI pipeline |
| [Git Workflow](architecture/git-workflow.md) | Branches, pull requests, CI pipeline, and how code gets merged |

---

## Other Resources

| Resource | Link |
|---|---|
| WPILib Docs (the official FRC programming bible) | https://docs.wpilib.org/en/stable/ |
| RobotPy (Python bindings for WPILib) | https://robotpy.readthedocs.io/ |
| Commands V2 (Python) | https://robotpy.readthedocs.io/projects/commands-v2/en/stable/ |
| pyfrc (simulation + testing) | https://robotpy.readthedocs.io/projects/pyfrc/en/stable/ |
| Skills Challenges (practice exercises) | https://github.com/Raptacon/Skills-Challenges |
| Controller Config Tool | [host/controller_config/ARCHITECTURE.md](../host/controller_config/ARCHITECTURE.md) |
| Hardware / CAN Layout | [subsystem/CAN_CONFIG.md](../subsystem/CAN_CONFIG.md) |

---

## Quick Reference

Most tasks can be done two ways — with `make` (shorter, runs the standard steps) or with the `python -m robotpy` command directly (more control, more options).

| Task | `make` shortcut | Direct Python command |
|---|---|---|
| First-time setup | `make` | `python -m venv venv && pip install -r requirements.txt && python -m robotpy sync` |
| Run simulator | `make sim` | `python -m robotpy sim` |
| Run all tests | `make test` | `python -m robotpy test` |
| Run tests with coverage | — | `python -m robotpy coverage test` |
| Run one test file | — | `python -m robotpy test -- tests/test_intake.py -v` |
| Run one test by name | — | `python -m robotpy test -- tests/test_intake.py::test_name -v` |
| Lint (check code style) | `make lint` | `flake8 . --count --select=E9,F6,F7,F8,F4,W1,W2,W4,W5,W6,E11 ...` |
| Sync libraries to robot | `make sync` | `python -m robotpy sync` |
| Deploy to robot | `make deploy` | `python -m robotpy deploy` |

> **Tip:** `make sim` runs tests first, then launches the simulator. `make deploy` runs sync then deploys. If you want to skip steps, use the Python commands directly.

---

## Contributing to the Docs

Found something confusing or out of date? Fix it! The docs live in `docs/` and use standard Markdown. Diagrams use [Mermaid](https://mermaid.js.org/) syntax, which renders automatically on GitHub and in VS Code (install the "Markdown Preview Mermaid Support" extension).
