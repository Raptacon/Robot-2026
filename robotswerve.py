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

# Third-party imports
import commands2
import wpilib
import wpimath
from commands2.button import Trigger
from pathplannerlib.auto import AutoBuilder

class RobotSwerve:
    """
    Container to hold the main robot code
    """
    # forward declare critical types for editors
    drivetrain: SwerveDrivetrain

    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        # networktables setup
        self.field = wpilib.Field2d()
        wpilib.SmartDashboard.putData("Field", self.field)

        # Subsystem instantiation
        self.drivetrain = SwerveDrivetrain()

        # Alliance instantiation
        self.updateAlliance()

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

        # HID setup
        wpilib.DriverStation.silenceJoystickConnectionWarning(True)
        self.driver_controller = wpilib.XboxController(0)
        self.mech_controller = wpilib.XboxController(1)

        # Autonomous setup
        self.auto_command = None
        self.auto_chooser = AutoBuilder.buildAutoChooser()
        wpilib.SmartDashboard.putData("Select auto routine", self.auto_chooser)

        # Telemetry setup
        wpilib.SmartDashboard.putNumber("Drivetrain speed", 1)
        self.enableTelemetry = wpilib.SmartDashboard.getBoolean("enableTelemetry", True)
        if self.enableTelemetry:
            self.telemetry = Telemetry(
                driveTrain=self.drivetrain, vision=self.vision
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
        self.updateAlliance()
        self.drivetrain.set_motor_stop_modes(to_drive=True, to_break=True, all_motor_override=True, burn_flash=False)
        self.drivetrain.stop_driving()

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        self.updateAlliance()
        self.auto_command = self.auto_chooser.getSelected()
        if self.auto_command:
            self.auto_command.schedule()
        else:
            self.drivetrain.reset_pose_estimator(self.drivetrain.get_default_starting_pose())

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        self.updateAlliance()
        if self.auto_command:
            self.auto_command.cancel()

        self.drivetrain.setDefaultCommand(
            DefaultDrive(
                self.drivetrain,
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getLeftY(), 0.06),
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getLeftX(), 0.06),
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getRightX(), 0.1),
                lambda: not self.driver_controller.getRightBumperButton()
            )
        )

    def teleopPeriodic(self):
        if self.driver_controller.getLeftTriggerAxis() > 0.5:
            commands2.CommandScheduler.getInstance().cancelAll()
        self.speedMultiplier = wpilib.SmartDashboard.getNumber("Drivetrain speed", 1)
        self.drivetrain.setSpeedMultiplier(self.speedMultiplier)

    def testInit(self):
        #TODO Move to NT listener on change listener
        self.updateAlliance()
        commands2.CommandScheduler.getInstance().cancelAll()
        self.drivetrain.setDefaultCommand(
            DefaultDrive(
                self.drivetrain,
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getLeftY(), 0.06),
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getLeftX(), 0.06),
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getRightX(), 0.1),
                lambda: not self.driver_controller.getRightBumperButton()
            )
        )
        commands2.cmd.run(lambda: self.drivetrain.drive(2, 0, 0, False), self.drivetrain).withTimeout(5).schedule()

    def testPeriodic(self):
        pass

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

    def updateAlliance(self) -> None:
        """
        Update the alliance the robot is on
        """
        self.alliance = wpilib.DriverStation.getAlliance()
        self.drivetrain.update_alliance_flag(self.alliance)

    def setAlignmentTag(self, alignmentTagId: int | None) -> None:
        """
        """
        self.alignmentTagId = alignmentTagId
