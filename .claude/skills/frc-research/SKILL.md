---
name: frc-research
description: Research FRC topics using primary sources -- WPILib docs, PhotonVision docs, REV/CTRE vendor docs, Chief Delphi, and team GitHub repos. Use when the user asks about FRC concepts, libraries, hardware, or wants to find how other teams solved a problem.
argument-hint: [topic to research]
---

# FRC Research Skill

Research the topic: **$ARGUMENTS**

Use the sources below in priority order. Fetch docs and search the web to gather
comprehensive, accurate information. Always cite your sources with links.

## Primary Documentation Sources

Search and fetch from these official docs first:

### WPILib (core FRC library)
- **Docs:** https://docs.wpilib.org/en/stable/
- **API (Java):** https://github.wpilib.org/allwpilib/docs/release/java/
- **Source:** https://github.com/wpilibsuite/allwpilib
- **RobotPy (Python bindings):** https://robotpy.readthedocs.io/en/stable/
- Covers: commands2 framework, kinematics, odometry, pose estimation, motor control,
  sensors, NetworkTables, simulation, autonomous, vision processing
- **Note:** Most examples are in Java/C++. Translate to Python for our codebase.
  Python uses snake_case methods and tuple args instead of Matrix/VecBuilder objects.

### PhotonVision (AprilTag vision)
- **Docs:** https://docs.photonvision.org/en/latest/
- **Python lib:** https://github.com/PhotonVision/photonvision/tree/main/photon-lib/py
- **Python examples:** https://github.com/PhotonVision/photonvision/tree/main/photonlib-python-examples
- Covers: camera setup, AprilTag pipelines, pose estimation, multi-tag, calibration

### REV Robotics (SparkMax / SparkFlex motor controllers)
- **REV Lib Docs:** https://docs.revrobotics.com/revlib
- **RobotPy REV API:** https://robotpy.readthedocs.io/projects/rev/en/stable/
- **Source:** https://github.com/REVrobotics/REVLib
- Covers: SparkMax/SparkFlex config, PID tuning, encoder setup, current limits,
  follower mode, idle mode, sim support

### CTRE (CANcoder, TalonFX, Pigeon)
- **Phoenix 6 Docs:** https://v6.docs.ctr-electronics.com/en/latest/
- **Python API:** https://api.ctr-electronics.com/phoenix6/release/python/
- Covers: CANcoder absolute encoders, TalonFX motors, Pigeon IMU, signal API,
  status codes, sim support

### PathPlanner (autonomous path planning)
- **Docs:** https://pathplanner.dev/home.html
- **API:** https://pathplanner.dev/api/python/
- **Source:** https://github.com/mjansen4857/pathern
- Covers: path creation, auto building, pathfinding, holonomic path following,
  named commands, event markers

### NavX (gyroscope/IMU)
- **Docs:** https://pdocs.kauailabs.com/navx-mxp/
- **RobotPy NavX:** https://robotpy.readthedocs.io/projects/navx/en/stable/

## Community Sources

After checking official docs, search these for real-world experience:

### Chief Delphi (FRC community forum)
- **URL:** https://www.chiefdelphi.com
- **Search:** `site:chiefdelphi.com $ARGUMENTS`
- Best for: practical advice, debugging help, design tradeoffs, "what worked for us"
- Look for posts from known strong teams (254, 1678, 6328, 3061, 971, 118)

### FRC Team GitHub Repositories
Search GitHub for working implementations. Priority teams for Python/swerve:

| Team | Repo / Search | Known for |
|------|--------------|-----------|
| **YAGSL** | `BroncBotz3481/YAGSL-Example` | Swerve library, vision integration |
| **3061 HuskieRobotics** | `HuskieRobotics/3061-lib` | Clean architecture, vision filtering |
| **254 Cheesy Poofs** | `Team254/FRC-2024-Public` | Reference-quality code |
| **6328 Mechanical Advantage** | `Mechanical-Advantage/RobotCode2024` | AdvantageKit logging, replay |
| **1678 Citrus Circuits** | `frc1678` | Swerve, vision, auto |
| **2910 Jack in the Bot** | `FRCTeam2910` | Swerve pioneer |

- **Search pattern:** `site:github.com FRC $ARGUMENTS python OR robotpy`
- **Also try:** `site:github.com FRC $ARGUMENTS java` (then translate to Python)

### FRC Discord
- Not searchable, but mention it as a resource if the user wants real-time help

## Research Process

1. **Start with official docs** -- fetch relevant pages from WPILib/vendor docs
2. **Find code examples** -- search GitHub for FRC team implementations
3. **Check Chief Delphi** -- search for practical experience and gotchas
4. **Synthesize** -- combine findings into a clear summary with:
   - How it works conceptually
   - Python API and code examples
   - Best practices and common pitfalls
   - Links to all sources consulted
5. **Relate to our codebase** -- note which files in this repo are relevant
   and how the findings could be applied

## Output Format

Structure your research as:

### Concept Overview
Brief explanation of what this is and why it matters.

### API and Usage (Python)
Code examples translated to Python/RobotPy for our codebase.

### Best Practices
What the docs and community recommend.

### Common Pitfalls
What teams have gotten wrong and how to avoid it.

### Relevant Files in This Repo
Which of our files relate to this topic.

### Sources
All links consulted, with brief description of what each provided.

## After Research

When research is complete, **offer to capture the findings** in a documentation
file in the relevant part of the codebase. For example:

- Tightly coupled to a subsystem -> doc next to that code
  (e.g. `subsystem/localization/VISION.md`, `subsystem/drivetrain/README.md`)
- General FRC concepts, cross-cutting topics, or reference material -> `docs/`
  (e.g. `docs/pathplanner.md`, `docs/pid-tuning.md`, `docs/sysid.md`)

Include: best practices, API usage, code examples, common pitfalls, and
links to all sources. This way future contributors (and future Claude sessions)
have the knowledge available without re-researching.

Ask the user: *"Want me to capture these findings in a doc? If so, where --
next to the relevant subsystem or in `docs/`?"*
