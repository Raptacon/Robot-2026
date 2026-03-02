"""
Container to hold the main robot code.

## Controller Map

![Driver Controller](./assets/2026bot_controller_map_page1.png)

![Operator Controller](./assets/2026bot_controller_map_page2.png)
"""

# Native imports
import json
import os
from pathlib import Path
from typing import Callable

# Internal imports
from data.telemetry import Telemetry
from vision import Vision
from commands.default_swerve_drive import DefaultDrive
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from utils.input import InputFactory

# Third-party imports
import commands2
import wpilib
from commands2.button import Trigger
from pathplannerlib.auto import AutoBuilder
from pathplannerlib.path import PathPlannerPath


class RobotSwerve:
    # forward declare critical types for editors
    drivetrain: SwerveDrivetrain

    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        # networktables setup
        self.field = wpilib.Field2d()
        wpilib.SmartDashboard.putData("Field", self.field)

        # Subsystem instantiation
        self.drivetrain = SwerveDrivetrain()
        
        # Alliance instantiaion
        self.alliance = "red" if self.drivetrain.flip_to_red_alliance() else "blue"

        # Vision setup
        try:
            self.vision = Vision(self.drivetrain)
        except Exception:
            self.vision = None
            wpilib.reportError("Unable to load vision class", printTrace=True)
        self.alignmentTagId = None
        self.caughtPeriodicVisionError = False

        # Initialize timer
        self.timer = wpilib.Timer()
        self.timer.start()

        # HID setup — config-driven via InputFactory
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

        # Autonomous setup
        self.auto_command = None
        self.auto_chooser = AutoBuilder.buildAutoChooser()
        wpilib.SmartDashboard.putData("Select auto routine", self.auto_chooser)

        self.teleop_stem_paths = {
            start_location: PathPlannerPath.fromPathFile(start_location)
            for start_location in [f"Stem_Reef_F{n}" for n in range(1, 7)] + [f"Stem_Reef_N{n}" for n in range(1, 7)]
        }

        # Telemetry setup
        wpilib.SmartDashboard.putNumber("Drivetrain speed", self._drive_scale_fast)
        self.enableTelemetry = wpilib.SmartDashboard.getBoolean("enableTelemetry", True)
        if self.enableTelemetry:
            self.telemetry = Telemetry(
                driveTrain=self.drivetrain, vision=self.vision,
                driverController=self.factory.getController(0),
                mechController=self.factory.getController(1),
            )

        wpilib.SmartDashboard.putString("Robot Version", self.getDeployInfo("git-hash"))
        wpilib.SmartDashboard.putString("Git Branch", self.getDeployInfo("git-branch"))
        wpilib.SmartDashboard.putString(
            "Deploy Host", self.getDeployInfo("deploy-host")
        )
        wpilib.SmartDashboard.putString(
            "Deploy User", self.getDeployInfo("deploy-user")
        )

        # Update drivetrain motor idle modes 3 seconds after the robot has been disabled.
        # to_break should be False at competitions where the robot is turned off between matches
        Trigger(is_disabled()).debounce(3).onTrue(
            commands2.cmd.runOnce(
                self.drivetrain.set_motor_stop_modes(
                    to_drive=True, to_break=True, all_motor_override=True, burn_flash=True
                ),
                self.drivetrain
            )
        )

    def robotPeriodic(self):
        self.factory.update()
        self._sync_control_telemetry()

        if self.enableTelemetry and self.telemetry:
            self.telemetry.runDefaultDataCollections()

        self.field.setRobotPose(self.drivetrain.current_pose())

        if self.vision is not None:
            try:
                self.vision.getCamEstimates(specificTagId=lambda: self.alignmentTagId)
                self.vision.showTargetData()
            except Exception:
                if not self.caughtPeriodicVisionError:
                    self.caughtPeriodicVisionError = True
                    wpilib.reportError("Retrieval of vision info failed in periodic", printTrace=True)

    def disabledInit(self):
        self.drivetrain.set_motor_stop_modes(to_drive=True, to_break=True, all_motor_override=True, burn_flash=False)
        self.drivetrain.stop_driving()

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        self.auto_command = self.auto_chooser.getSelected()
        if self.auto_command:
            self.auto_command.schedule()
        else:
            self.drivetrain.reset_pose_estimator(self.drivetrain.get_default_starting_pose())

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        if self.auto_command:
            self.auto_command.cancel()

        self.alliance = "blue"
        if self.drivetrain.flip_to_red_alliance():
            self.alliance = "red"
        self.teleop_auto_command = None

        self.drivetrain.setDefaultCommand(
            DefaultDrive(
                self.drivetrain,
                self.translate_x,
                self.translate_y,
                self.rotate,
                lambda: not self.robot_relative_btn()
            )
        )

    def teleopPeriodic(self):
        pass

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
            commands2.cmd.runOnce(lambda: self._toggle_drive_scale())
        )

    def _set_drive_scale(self, scale: float) -> None:
        """Set scale on all drive axes and publish to SmartDashboard."""
        for analog in (self.translate_x, self.translate_y, self.rotate):
            analog.scale = scale
            if hasattr(analog, 'nt_scale'):
                analog.nt_scale = scale
        wpilib.SmartDashboard.putNumber("Drivetrain speed", scale)

    def _toggle_drive_scale(self) -> None:
        """Toggle between slow and fast drive scale presets."""
        self._drive_is_slow = not self._drive_is_slow
        scale = self._drive_scale_slow if self._drive_is_slow else self._drive_scale_fast
        self._set_drive_scale(scale)

    def _sync_control_telemetry(self) -> None:
        """Read control tuning values from NT and apply to managed inputs.

        Keeps speed control logic visible at the robot container level.
        The SmartDashboard "Drivetrain speed" value is the authoritative
        source — if a dashboard user changes it, that overrides the
        toggle preset. The Y button toggle writes to SmartDashboard too,
        so both paths converge here.

        This will be refactored later when the factory supports indirect
        network bindings natively.
        """
        nt_speed = wpilib.SmartDashboard.getNumber(
            "Drivetrain speed", self._drive_scale_fast)
        for analog in (self.translate_x, self.translate_y, self.rotate):
            if analog.scale != nt_speed:
                analog.scale = nt_speed
                if hasattr(analog, 'nt_scale'):
                    analog.nt_scale = nt_speed

    def getDeployInfo(self, key: str) -> str:
        """Gets the Git SHA of the deployed robot by parsing ~/deploy.json and returning the git-hash from the JSON key OR if deploy.json is unavailable will return "unknown"
            example deploy.json: '{"deploy-host": "DESKTOP-80HA89O", "deploy-user": "ehsra", "deploy-date": "2023-03-02T17:54:14", "code-path": "blah", "git-hash": "3f4e89f138d9d78093bd4869e0cac9b61becd2b9", "git-desc": "3f4e89f-dirty", "git-branch": "fix-recal-nbeasley"}

        Args:
            key (str): The desired json key to get. Popular onces are git-hash, deploy-host, deploy-user

        Returns:
            str: Returns the value of the desired deploy key
        """
        json_object = None
        home = str(Path.home()) + os.path.sep
        releaseFile = home + 'py' + os.path.sep + "deploy.json"
        try:
            # Read from ~/deploy.json
            with open(releaseFile, "r") as openfile:
                json_object = json.load(openfile)
                print(json_object)
                print(type(json_object))
                if key in json_object:
                    return json_object[key]
                else:
                    return f"Key: {key} Not Found in JSON"
        except OSError:
            return "unknown"
        except json.JSONDecodeError:
            return "bad json in deploy file check for unescaped "

    def setAlignmentTag(self, alignmentTagId: int | None) -> None:
        """
        """
        self.alignmentTagId = alignmentTagId
