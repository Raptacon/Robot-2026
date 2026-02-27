# Native imports
import logging

# Internal imports
from data.telemetry import Telemetry
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from subsystem.manifest import ROBOT_MANIFESTS
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
    # forward declare critical types for editors
    drivetrain: SwerveDrivetrain

    # Persistent robot name — operators can change in the dashboard
    robot_name = ntproperty("/robot/name", "competition",
                            writeDefault=False, persistent=True)

    def __init__(self) -> None:
        # HID setup (must come before registry so controls modules can access controllers)
        wpilib.DriverStation.silenceJoystickConnectionWarning(True)
        self.driver_controller = wpilib.XboxController(0)
        self.mech_controller = wpilib.XboxController(1)

        # Build manifest and create registry (container=self for controls discovery)
        manifest_builder = ROBOT_MANIFESTS.get(
            self.robot_name, ROBOT_MANIFESTS[None]
        )
        manifest = manifest_builder(self)
        self.registry = SubsystemRegistry(manifest, container=self)

        # Auto-populate self.<name> for every active subsystem
        for name, instance in self.registry.active_subsystems.items():
            setattr(self, name, instance)

        # Autonomous setup
        self.auto_command = None
        self.auto_chooser = AutoBuilder.buildAutoChooser()
        wpilib.SmartDashboard.putData("Select auto routine", self.auto_chooser)

        self.teleop_stem_paths = {
            start_location: PathPlannerPath.fromPathFile(start_location)
            for start_location in [f"Stem_Reef_F{n}" for n in range(1, 7)] + [f"Stem_Reef_N{n}" for n in range(1, 7)]
        }

        # Telemetry setup (controller + driverstation logging)
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
        self.registry.run_all_disabled_init()

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        self.auto_command = self.auto_chooser.getSelected()
        if self.auto_command:
            self.auto_command.schedule()
        elif self.drivetrain is not None:
            self.drivetrain.reset_pose_estimator(self.drivetrain.get_default_starting_pose())

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
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
