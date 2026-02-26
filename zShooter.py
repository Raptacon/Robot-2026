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
import typing

class RobotSwerve:
    """
    Container to hold the main robot code
    """
    # forward declare critical types for editors
    drivetrain: SwerveDrivetrain
    
    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        self.shooter = Shooter()
        self.configs = rev.SparkBaseConfig()
        self.robotConfigs = OperatorRobotConfig()
        self.xbox = commands2.button.CommandXboxController(0)
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
        # For tuning
        wpilib.SmartDashboard.putNumberArray("Intake PIDF", [0, 0, 0, 0])
        wpilib.SmartDashboard.putNumberArray("Top PIDF", [0, 0, 0, 0])
        wpilib.SmartDashboard.putNumberArray("Bottom PIDF", [0, 0, 0, 0])

    def teleopPeriodic(self):
        wpilib.SmartDashboard.putNumber("In_Velocity", self.shooter.getVelocity('intake'))
        wpilib.SmartDashboard.putNumber("Top_Velocity", self.shooter.getVelocity('top'))
        wpilib.SmartDashboard.putNumber("Bottom_Velocity", self.shooter.getVelocity('bottom'))

        # Offset RPM by +100
        self.xbox.povUp().onTrue(commands2.cmd.runOnce(lambda: self.shooter.increaseOffset, self.shooter))
        # Offset RPM by -100
        self.xbox.povDown().onTrue(commands2.cmd.runOnce(lambda: self.shooter.decreaseOffset, self.shooter))

    def testInit(self):
        commands2.CommandScheduler.getInstance().cancelAll()

    def testPeriodic(self):
        # For tuning robot
        self.xbox.x().onTrue(commands2.cmd.parallel(           
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('intake', 0), self.shooter),
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('top', 0), self.shooter),
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('bottom', 0), self.shooter))
        )

        self.xbox.x().onTrue(commands2.cmd.parallel(            
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('intake', 3000), self.shooter),
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('top', 3000), self.shooter),
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('bottom', 3000), self.shooter))
        )

        self.xbox.x().onTrue(commands2.cmd.parallel(            
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('intake', 4000), self.shooter),
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('top', 4500), self.shooter),
            commands2.cmd.runOnce(lambda: self.shooter.setMotorReference('bottom', 4500), self.shooter))
        )

        self.intakeMotorPIDF: typing.Tuple[float, float, float, float] = wpilib.SmartDashboard.getNumberArray("Intake PIDF", [0, 0, 0, 0])
        self.topMotorPIDF: typing.Tuple[float, float, float, float] = wpilib.SmartDashboard.getNumberArray("Top PIDF", [0, 0, 0, 0])
        self.bottomMotorPIDF: typing.Tuple[float, float, float, float] = wpilib.SmartDashboard.getNumberArray("Bottom PIDF", [0, 0, 0, 0])

        self.configs.closedLoop.pidf(*self.intakeMotorPIDF, rev.ClosedLoopSlot.kSlot0)
        self.shooter.intakeMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        
        self.configs.closedLoop.pidf(*self.topMotorPIDF, rev.ClosedLoopSlot.kSlot0)
        self.shooter.topMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        
        self.configs.closedLoop.pidf(*self.bottomMotorPIDF, rev.ClosedLoopSlot.kSlot0)
        self.shooter.bottomMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)

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
