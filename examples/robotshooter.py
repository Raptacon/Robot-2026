# Native imports
import json
import os
from pathlib import Path
from typing import Callable
import typing

# Internal imports
from config import ShooterConfig
from subsystem.shooter import Shooter

# Third-party imports
import commands2
import rev
import wpilib


class RobotShooter:
    """
    Container to hold the main robot code
    """
    
    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        self.shooter = Shooter()
        self.configs = rev.SparkBaseConfig()
        self.xbox = commands2.button.CommandXboxController(0)

    def robotPeriodic(self):
        pass

    def disabledInit(self):
        self.shooter.setRPM(0)
        self.shooter.resetOffset()
        for motor in ["feed", "lead", "follower"]:
            self.shooter.setMotorVoltage(motor, 0)

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        pass

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        # Increase target RPM
        self.xbox.povUp().onTrue(commands2.cmd.runOnce(lambda: self.shooter.modifyOffset(ShooterConfig.shooterOffsetDelta), self.shooter))
        # Decrease target RPM
        self.xbox.povDown().onTrue(commands2.cmd.runOnce(lambda: self.shooter.modifyOffset(-ShooterConfig.shooterOffsetDelta), self.shooter))

        # TODO: calculate range based on odometry
        # Crashes robotpy sim
        # self.shooter.setDefaultCommand(self.shooter, lambda: self.shooter.setRpmUsingLookup(1))

    def teleopPeriodic(self):
        wpilib.SmartDashboard.putNumber("Feed_Velocity", self.shooter.getVelocity('feed'))
        wpilib.SmartDashboard.putNumber("Lead_Fly_Velocity", self.shooter.getVelocity('lead'))
        wpilib.SmartDashboard.putNumber("Follower_Fly_Velocity", self.shooter.getVelocity('follower'))



    def testInit(self):
        commands2.CommandScheduler.getInstance().cancelAll()

        # For tuning shooter
        wpilib.SmartDashboard.putNumberArray("Feed PIDF", [0, 0, 0, 0])
        wpilib.SmartDashboard.putNumberArray("Lead Flywheel PIDF", [0, 0, 0, 0])

        self.lastFeedPIDF = (0, 0, 0, 0)
        self.lastFlywheelPIDF = (0, 0, 0, 0)

        self.xbox.x().onTrue(
            commands2.cmd.runOnce(lambda: self.shooter.setRPM(0), self.shooter)
        )

        self.xbox.a().onTrue(
            commands2.cmd.runOnce(lambda: self.shooter.setRPM(3000), self.shooter)
        )

        self.xbox.b().onTrue(
            commands2.cmd.runOnce(lambda: self.shooter.setRPM(4500), self.shooter)
        )

        self.xbox.y().onTrue(
            commands2.cmd.runOnce(self.shooter.resetOffset, self.shooter)
        )

    def testPeriodic(self):
        self.feedMotorPIDF: typing.Tuple[float, float, float, float] = tuple(wpilib.SmartDashboard.getNumberArray("Feed PIDF", [0, 0, 0, 0]))
        self.leadFlywheelMotorPIDF: typing.Tuple[float, float, float, float] = tuple(wpilib.SmartDashboard.getNumberArray("Lead Flywheel PIDF", [0, 0, 0, 0]))

        if self.feedMotorPIDF != self.lastFeedPIDF:
            self.configs.closedLoop.pidf(*self.feedMotorPIDF, rev.ClosedLoopSlot.kSlot0)
            self.shooter.motors["feed"].configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)

        if self.leadFlywheelMotorPIDF != self.lastFlywheelPIDF:
            self.configs.closedLoop.pidf(*self.leadFlywheelMotorPIDF, rev.ClosedLoopSlot.kSlot0)
            self.shooter.motors["lead"].configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)

        self.lastFeedPIDF = self.feedMotorPIDF
        self.lastFlywheelPIDF = self.leadFlywheelMotorPIDF

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
