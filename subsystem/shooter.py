from config import ShooterConfig
from constants.field_target_constants import FieldTargets
import rev
import wpilib
from commands2 import Subsystem
from typing import Dict, Callable
from enum import StrEnum
import numpy as np
from wpimath.geometry import Pose2d, Translation2d

class ShooterMotorNames(StrEnum):
    """
    Create consistent names for shooter motor references
    """

    FEED = "feed"
    LEAD_FLYWHEEL = "lead"
    FOLLOWER_FLYWHEEL = "follower"


class FlywheelModes(StrEnum):
    """
    Create consistent names for flywheel operating modes
    """

    AUTO_RPM = "autoRPM"
    FIXED_RPM = "fixedRPM"


class Shooter(Subsystem):
    def __init__(self):
        super().__init__()
        self.offsetAmount = 0
        self.offsetDelta = 0
        self.RPM = 0
        self.flywheelMode = FlywheelModes.AUTO_RPM
        self.feedActive = False
        self.flywheelActive = False

        # Create lookup table (distance, RPM)
        self.lookupTable = [
            (0.0, 1000),
            (1.0, 1500),
            (2.0, 2000),
            (3.0, 3000),
            (4.0, 3500),
            (5.0, 4000),
            ]
        self.lookupTable.sort()
        # Create an array of just distances
        self.lookupShooterDistances = np.array([d for d, _ in self.lookupTable])
        # Create an array of just RPMs
        self.lookupShooterRpms = np.array([r for _, r in self.lookupTable])

        # Instantiate motors
        self.feedMotor = rev.SparkMax(30, rev.SparkLowLevel.MotorType.kBrushless)
        self.leadFlywheelMotor = rev.SparkFlex(32, rev.SparkLowLevel.MotorType.kBrushless)
        self.followerFlywheelMotor = rev.SparkFlex(33, rev.SparkLowLevel.MotorType.kBrushless)

        # Set up configs for each motor
        self.configureMotor(self.feedMotor, ShooterConfig.shooterFeedMotorPIDF, ShooterConfig.shooterInverted[0])
        self.configureMotor(self.leadFlywheelMotor, ShooterConfig.shooterFlywheelMotorPIDF, ShooterConfig.shooterInverted[1])
        self.configureMotor(self.followerFlywheelMotor, ShooterConfig.shooterFlywheelMotorPIDF, ShooterConfig.shooterInverted[2], self.leadFlywheelMotor)

        self.motors: Dict[str, rev.SparkFlex | rev.SparkMax] = {
            ShooterMotorNames.FEED: self.feedMotor,
            ShooterMotorNames.LEAD_FLYWHEEL: self.leadFlywheelMotor,
            ShooterMotorNames.FOLLOWER_FLYWHEEL: self.followerFlywheelMotor
        }

        # Get encoders from each motor to read data
        self.feedEncoder = self.feedMotor.getEncoder()
        self.leadFlywheelEncoder = self.leadFlywheelMotor.getEncoder()
        self.followerFlywheelEncoder = self.followerFlywheelMotor.getEncoder()
        self.encoders = {
            ShooterMotorNames.FEED: self.feedEncoder,
            ShooterMotorNames.LEAD_FLYWHEEL: self.leadFlywheelEncoder,
            ShooterMotorNames.FOLLOWER_FLYWHEEL: self.followerFlywheelEncoder
        }

        # Create closed loop controllers to be able to set a reference/goal for pid
        self.feedPID = self.feedMotor.getClosedLoopController()
        self.leadFlywheelPID = self.leadFlywheelMotor.getClosedLoopController()
        self.PIDs = {
            ShooterMotorNames.FEED: self.feedPID,
            ShooterMotorNames.LEAD_FLYWHEEL: self.leadFlywheelPID,
            # Avoid key errors
            ShooterMotorNames.FOLLOWER_FLYWHEEL: self.leadFlywheelPID,
        }

    def configureMotor(
        self, motor: rev.SparkFlex | rev.SparkMax,
        pidf: tuple,
        invert: bool,
        leader: rev.SparkFlex | rev.SparkMax = None
    ):
        """
        Configure the PIDF constants and inversion for the given motor.
        
        Args:
            motor: the motor on the shooter to configure
            pidf: the PIDF constants to set on the given motor
            invert: if True, invert the rotation direction of the given motor
            leader: the motor to follow. If None, do not set this motor as a follower

        Returns:
            None
        """
        configs = rev.SparkBaseConfig()

        if leader is not None:
            configs.follow(leader=leader, invert=invert)
        else:
            configs.inverted(invert)
            configs.closedLoop.pidf(*pidf, rev.ClosedLoopSlot.kSlot0)

        motor.configure(configs, rev.ResetMode.kResetSafeParameters, rev.PersistMode.kPersistParameters)

    def setMotorVoltage(self, motorName: str, voltage: float):
        """
        Sets the voltage of the motor

        Args:
            motorName: Name of the motor to set a voltage for (ie: 'feed')
            voltage: Voltage to set the motor at

        Returns:
            None
        """
        self.motors[motorName].setVoltage(voltage)

    def setMotorReference(self, motorName: str, rpm: float):
        """
        Give a custom setpoint for PID to achieve in terms of velocity

        Args:
            motorName: Name of the motor
            rpm: The velocity setpoint for the motor in RPM

        Returns:
            None
        """
        self.PIDs[motorName].setReference(rpm, rev.SparkLowLevel.ControlType.kVelocity, rev.ClosedLoopSlot.kSlot0)

    def setRPM(self, rpm: float):
        """
        Directly set the RPM using the given value

        Args:
            rpm: The velocity setpoint for the motor in RPM

        Returns:
            None
        """
        self.RPM = rpm

    def getVelocity(self, motorName: str):
        """
        Get the current velocity of a motor in RPM

        Args:
            motorName: Name of the motor

        Returns:
            Velocity of the motor in RPM
        """
        return self.encoders[motorName].getVelocity()

    def setRpmUsingLookup(self, distance: float):
        """
        Set the RPM needed to shoot the ball at a specified distance

        Args:
            distance: distance in meters from a target point

        Returns:
            None
        """
        # Get RPM from the distance given
        self.RPM = float(np.interp(distance, self.lookupShooterDistances, self.lookupShooterRpms))

    def modifyOffset(self, offsetDelta: float):
        """
        Modify the RPM offset

        Args:
            offsetDelta: change in offset that is applied

        Returns:
            None
        """
        self.offsetDelta = offsetDelta
        self.offsetAmount = self.offsetAmount + self.offsetDelta

    def resetOffset(self):
        """
        Reset the RPM offset

        Args:
            None

        Returns:
            None
        """
        self.offsetAmount = 0

    def getOffset(self):
        """
        Get the RPM offset

        Args:
            None

        Returns:
            None
        """
        return self.offsetAmount

    def getFlywheelMode(self):
        return self.flywheelMode

    def cycleFlywheelMode(self):
        if self.flywheelMode == FlywheelModes.AUTO_RPM:
            self.flywheelMode = FlywheelModes.FIXED_RPM
        elif self.flywheelMode == FlywheelModes.FIXED_RPM:
            self.flywheelMode = FlywheelModes.AUTO_RPM

    def toggleFlywheelActive(self):
        self.flywheelActive = not self.flywheelActive

    def toggleFeedActive(self):
        self.feedActive = not self.feedActive

    def calculateRangeFromOdometry(self, odometry: Callable[[],Pose2d], alliance: wpilib.DriverStation.Alliance):
        self.odometryTranslation = odometry().translation()
        target = Translation2d(8.270494, 4.034536)
        if alliance == wpilib.DriverStation.Alliance.kRed:
            if self.odometryTranslation.X() > FieldTargets.redHubTarget[0]: 
                target = FieldTargets.redHubTarget
            elif self.odometryTranslation.Y() < FieldTargets.redHubTarget[1]:
                target = FieldTargets.bottomRightTarget
            else:
                target = FieldTargets.topRightTarget
        else:
            if self.odometryTranslation.X() < FieldTargets.blueHubTarget[0]:
                target = FieldTargets.blueHubTarget
            elif self.odometryTranslation.Y() < FieldTargets.blueHubTarget[1]:
                target = FieldTargets.bottomLeftTarget
            else:
                target = FieldTargets.topLeftTarget
        range = self.odometryTranslation.distance(target)

        return abs(range)

    def periodic(self):
        newRPM = self.RPM + self.offsetAmount
        if self.feedActive:
            feedRPM = int(newRPM * ShooterConfig.shooterFeedPercentOfFlywheel)
            self.setMotorReference(ShooterMotorNames.FEED, feedRPM)
        else:
            feedRPM = 0
            self.setMotorVoltage(ShooterMotorNames.FEED, 0)

        if self.flywheelActive:
            self.setMotorReference(ShooterMotorNames.LEAD_FLYWHEEL, newRPM)
        else:
            newRPM = 0
            self.setMotorVoltage(ShooterMotorNames.LEAD_FLYWHEEL, 0)

        wpilib.SmartDashboard.putNumber("Shooter_RPM", newRPM)
        wpilib.SmartDashboard.putNumber("Shooter_Feed_RPM", feedRPM)
        wpilib.SmartDashboard.putNumber("Shooter_Offset", self.offsetAmount)
        wpilib.SmartDashboard.putNumber("Offset_Delta", self.offsetDelta)
        wpilib.SmartDashboard.putBoolean("Feed_Active", self.feedActive)
        wpilib.SmartDashboard.putBoolean("Flywheel_Active", self.flywheelActive)
        wpilib.SmartDashboard.putString("Flywheel_Mode", self.flywheelMode)
