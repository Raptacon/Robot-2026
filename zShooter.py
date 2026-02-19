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
from config import OperatorRobotConfig

# Third-party imports
import commands2
import rev
import wpilib
import wpimath
from commands2.button import Trigger
from pathplannerlib.auto import AutoBuilder
from pathplannerlib.path import PathPlannerPath
from subsystem.z_Shooter import zShooter as Shooter
class RobotSwerve:
    """
    Container to hold the main robot code
    """
    # forward declare critical types for editors
    drivetrain: SwerveDrivetrain
    
    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        self.shooter = Shooter()
    def robotPeriodic(self):
        pass
    def disabledInit(self):
        pass
    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        pass
    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        pass

    def teleopPeriodic(self):
        if wpilib.XboxController(0).getAButtonPressed:
            self.shooter.setMotorReference('intake', 1000)
            self.shooter.setMotorReference('top', 1000)
            self.shooter.setMotorReference('bottom', 1000)

        self.intakeVelocity = self.shooter.intakeEncoder.getVelocity()
        self.topVelocity = self.shooter.topEncoder.getVelocity()
        self.bottomVelocity = self.shooter.bottomEncoder.getVelocity()

        wpilib.SmartDashboard.putNumber("In_Velocity", self.intakeVelocity)
        wpilib.SmartDashboard.putNumber("Top_Velocity", self.topVelocity)
        wpilib.SmartDashboard.putNumber("Bottom_Velocity", self.bottomVelocity)

    def testInit(self):
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

    def isArmSafe(self) -> bool:
        """
        """
        return True

    def setAlignmentTag(self, alignmentTagId: int | None) -> None:
        """
        """
        self.alignmentTagId = alignmentTagId
