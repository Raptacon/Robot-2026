# Native imports
import json
import os
from pathlib import Path
from typing import Callable

# Third-party imports
import commands2
import wpilib
import wpimath

# --- Drivetrain stub for testing log uploader without CAN hardware ---
class _DrivetrainStub:
    def update_alliance_flag(self, alliance): pass
    def current_pose(self): return wpimath.geometry.Pose2d()
    def set_motor_stop_modes(self, **kwargs): return lambda: None
    def stop_driving(self): pass
    def reset_pose_estimator(self, pose): pass
    def setDefaultCommand(self, cmd): pass
    def setSpeedMultiplier(self, s): pass
    def drive(self, *a, **kw): pass
    def get_default_starting_pose(self): return wpimath.geometry.Pose2d()


class RobotSwerve:
    """
    Container to hold the main robot code
    """

    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        # networktables setup
        self.field = wpilib.Field2d()
        wpilib.SmartDashboard.putData("Field", self.field)

        # Subsystem instantiation (stubbed for log uploader testing)
        self.drivetrain = _DrivetrainStub()
        self.vision = None
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

        wpilib.SmartDashboard.putString("Robot Version", self.getDeployInfo("git-hash"))
        wpilib.SmartDashboard.putString("Git Branch", self.getDeployInfo("git-branch"))

    def robotPeriodic(self):
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

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        self.updateAlliance()
        if self.auto_command:
            self.auto_command.cancel()

    def teleopPeriodic(self):
        if self.driver_controller.getLeftTriggerAxis() > 0.5:
            commands2.CommandScheduler.getInstance().cancelAll()
        self.speedMultiplier = wpilib.SmartDashboard.getNumber("Drivetrain speed", 1)
        self.drivetrain.setSpeedMultiplier(self.speedMultiplier)

    def testInit(self):
        self.updateAlliance()
        commands2.CommandScheduler.getInstance().cancelAll()

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
