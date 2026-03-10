"""
Container to hold the main robot code.

## Controller Map

![Driver Controller](./assets/2026bot_controller_map_page1.png)

![Operator Controller](./assets/2026bot_controller_map_page2.png)
"""

# Native imports
import logging

# Internal imports
from data.telemetry import Telemetry
from subsystem.manifest import ROBOT_MANIFESTS
from utils.input import InputFactory
from utils.subsystem_factory import SubsystemRegistry

# Third-party imports
import commands2
import wpilib
from ntcore.util import ntproperty
from pathplannerlib.auto import AutoBuilder
from pathplannerlib.path import PathPlannerPath


logger = logging.getLogger(__name__)


class RobotSwerve:
    """
    Container to hold the main robot code.

    Uses SubsystemRegistry to manage subsystem lifecycle:
    creation, controls, telemetry, and disabled behavior are
    handled via convention-based discovery on each subsystem.
    """
    # Default to None so lifecycle methods work when subsystem creation fails
    drivetrain = None

    # Persistent robot name — operators can change in the dashboard
    robot_name = ntproperty("/robot/name", "competition",
                            writeDefault=False, persistent=True)

    def __init__(self) -> None:
        # HID setup (must come before registry so controls modules can access controllers)
        wpilib.DriverStation.silenceJoystickConnectionWarning(True)
        self.factory = InputFactory(config_path="data/inputs/2026bot.yaml")

        # Speed toggle state
        self._drive_scale_slow = 0.25
        self._drive_scale_fast = 1
        self._drive_is_slow = False

        # TODO: Move input retrieval and binding into commands/{subsystem}_controls.py
        # files as part of the subsystem registry refactor. Each subsystem's controls
        # module should own its own factory.get*() calls and command wiring.
        self._configure_controls()

        # Build manifest and create registry (container=self for controls discovery)
        manifest_builder = ROBOT_MANIFESTS.get(
            self.robot_name, ROBOT_MANIFESTS[None]
        )
        manifest = manifest_builder(self)
        self.registry = SubsystemRegistry(manifest, container=self)

        # Auto-populate self.<name> for every active subsystem
        for name, instance in self.registry.active_subsystems.items():
            setattr(self, name, instance)

        # Autonomous setup (requires drivetrain for PathPlanner configuration)
        self.auto_command = None
        self.auto_chooser = None
        self.teleop_stem_paths = {}

        if self.drivetrain is not None:
            self.auto_chooser = AutoBuilder.buildAutoChooser()
            wpilib.SmartDashboard.putData("Select auto routine", self.auto_chooser)

            self.teleop_stem_paths = {
                start_location: PathPlannerPath.fromPathFile(start_location)
                for start_location in [f"Stem_Reef_F{n}" for n in range(1, 7)] + [f"Stem_Reef_N{n}" for n in range(1, 7)]
            }

        # Telemetry setup (controller + driverstation logging)
        wpilib.SmartDashboard.putNumber("Drivetrain speed", self._drive_scale_fast)
        self.enableTelemetry = wpilib.SmartDashboard.getBoolean("enableTelemetry", True)
        if self.enableTelemetry:
            self.telemetry = Telemetry()

        # Register all subsystem controls (auto-discovered from commands/{name}_controls.py)
        self.registry.register_all_controls()

    # ---- Robot lifecycle ----

    def robotPeriodic(self):
        if self.enableTelemetry and self.telemetry:
            self.telemetry.runDefaultDataCollections()

        self.registry.run_all_telemetry()

    def disabledInit(self):
        self.updateAlliance()
        self.registry.run_all_disabled_init()

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        self.updateAlliance()
        if self.auto_chooser is not None:
            self.auto_command = self.auto_chooser.getSelected()
        if self.auto_command:
            self.auto_command.schedule()
        elif self.drivetrain is not None:
            self.drivetrain.reset_pose_estimator(self.drivetrain.get_default_starting_pose())

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        self.updateAlliance()
        if self.auto_command:
            self.auto_command.cancel()

        self.teleop_auto_command = None

        self.registry.run_all_teleop_init()

    def teleopPeriodic(self):
        self.registry.run_all_teleop_periodic()

    def testInit(self):
        commands2.CommandScheduler.getInstance().cancelAll()

    def testPeriodic(self):
        pass

    def _configure_controls(self) -> None:
        """Retrieve managed inputs from the factory and wire command bindings.

        TODO: Move into commands/{subsystem}_controls.py files as part of the
        subsystem registry refactor. Each subsystem's controls module would
        call register_controls(subsystem, container) and own its own
        factory.get*() calls and command wiring.
        """
        # Managed drive inputs
        self.translate_x = self.factory.getAnalog("drivetrain.translate_x")
        self.translate_y = self.factory.getAnalog("drivetrain.translate_y")
        self.rotate = self.factory.getAnalog("drivetrain.rotate")
        self.robot_relative_btn = self.factory.getRawButton("drivetrain.robot_relative")

        # Cancel-all: event-driven via Trigger instead of polling
        self.factory.getButton("drivetrain.cancel_all").onTrue(
            commands2.cmd.runOnce(
                lambda: commands2.CommandScheduler.getInstance().cancelAll()
            )
        )

        # Speed toggle: Y button switches between slow and fast scale
        self.factory.getButton("drivetrain.speed_toggle").onTrue(
            commands2.cmd.runOnce(self._toggle_drive_scale)
        )

        # Map all drive axes' scale to a shared SmartDashboard entry.
        # Dashboard changes and Y-button toggles both write to this path;
        # the factory auto-syncs the value into all three analogs each cycle.
        _SPEED_NT = "/SmartDashboard/Drivetrain speed"
        for analog in (self.translate_x, self.translate_y, self.rotate):
            analog.mapParamToNtPath(_SPEED_NT, "scale")

    def _toggle_drive_scale(self) -> None:
        """Toggle between slow and fast drive scale presets.

        Writes the new scale to SmartDashboard; the factory auto-syncs
        it into all three drive analogs via mapParamToNtPath each cycle.
        """
        self._drive_is_slow = not self._drive_is_slow
        scale = self._drive_scale_slow if self._drive_is_slow else self._drive_scale_fast
        wpilib.SmartDashboard.putNumber("Drivetrain speed", scale)

    def updateAlliance(self) -> None:
        """
        Update the alliance the robot is on
        """
        self.alliance = wpilib.DriverStation.getAlliance()
        if self.drivetrain is not None:
            self.drivetrain.update_alliance_flag(self.alliance)
