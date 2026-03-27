# Native imports
from enum import StrEnum
import numpy as np
from typing import Dict, Callable

# Internal imports
from config import ShooterConfig
from constants.swerve_constants import PancakeShooterConstants

# Third-party imports
from commands2 import Subsystem
import rev
import wpilib
from wpimath.geometry import Pose2d, Translation2d

class ShooterMotorNames(StrEnum):
    """
    Create consistent names for shooter motor references
    """

    LEAD_FLYWHEEL = "lead_flywheel"
    FOLLOWER_FLYWHEEL = "follower_flywheel"
    LEAD_FEED = "lead_feed"
    FOLLOWER_FEED = "follower_feed"

class FlywheelModes(StrEnum):
    """
    Create consistent names for flywheel operating modes
    """

    AUTO_RPM = "autoRPM"
    FIXED_RPM = "fixedRPM"

class FixedShootingPositions(StrEnum):
    """
    Define a set of postiions on the field to tie fixed RPMs to
    """

    DEFAULT = "default"
    HUB = "hub"
    TOWER = "tower"
    ALLIANCE_CORNER = "alliance_corner"
    CLOSE_FEED = "close_feed"
    MID_FEED = "mid_feed"
    FAR_FEED = "far_feed"

class TargetMode(StrEnum):
    """
    Target profile for distance-based RPM and hood angle lookup.
    """

    AIR = "air"
    GROUND = "ground"

class Shooter(Subsystem):
    def __init__(self):
        super().__init__()
        self.offsetAmount = 0
        self.offsetDelta = 0
        self.RPM = 0
        self.targetDistance = 0.0
        self.flywheelMode = FlywheelModes.FIXED_RPM
        self.targetMode = TargetMode.AIR
        self.fixedRPMPosition = FixedShootingPositions.DEFAULT
        self.feedActive = False
        self.flywheelActive = False

        # Lookup tables: (distance_meters, rpm, hood_angle_degrees)
        self.airTargetTable = [
            (0.0, 1000, 5.0),
            (1.0, 1500, 10.0),
            (2.0, 2000, 15.0),
            (3.0, 3000, 20.0),
            (4.0, 3500, 25.0),
            (5.0, 4000, 30.0),
        ]
        self.airTargetTable.sort()
        self.airDistances = np.array([d for d, _, _ in self.airTargetTable])
        self.airRpms = np.array([r for _, r, _ in self.airTargetTable])
        self.airAngles = np.array([a for _, _, a in self.airTargetTable])

        self.groundTargetTable = [
            (0.0, 1000, 0.0),
            (1.0, 1500, 5.0),
            (2.0, 2000, 10.0),
            (3.0, 3000, 15.0),
            (4.0, 3500, 20.0),
            (5.0, 4000, 25.0),
        ]
        self.groundTargetTable.sort()
        self.groundDistances = np.array([d for d, _, _ in self.groundTargetTable])
        self.groundRpms = np.array([r for _, r, _ in self.groundTargetTable])
        self.groundAngles = np.array([a for _, _, a in self.groundTargetTable])

        # Create a lookup for fixed location RPMs
        self.lookupFixedPositionRPMs = {
            FixedShootingPositions.DEFAULT: 3000,
            FixedShootingPositions.HUB: 1500,
            FixedShootingPositions.TOWER: 2250,
            FixedShootingPositions.ALLIANCE_CORNER: 3500,
            FixedShootingPositions.CLOSE_FEED: 1750,
            FixedShootingPositions.MID_FEED: 2750,
            FixedShootingPositions.FAR_FEED: 4500,
        }

        # Instantiate motors
        self.leadFlywheelMotor = rev.SparkFlex(PancakeShooterConstants.flywheelLeadMotorId, rev.SparkLowLevel.MotorType.kBrushless)
        self.followerFlywheelMotor = rev.SparkFlex(PancakeShooterConstants.flywheelFollowerMotorId, rev.SparkLowLevel.MotorType.kBrushless)
        self.leadFeedMotor = rev.SparkMax(PancakeShooterConstants.feedLeadMotorId, rev.SparkLowLevel.MotorType.kBrushless)
        self.followerFeedMotor = rev.SparkMax(PancakeShooterConstants.feedFolowerMotorId, rev.SparkLowLevel.MotorType.kBrushless)

        # Set up configs for each motor
        self.configureMotor(self.leadFlywheelMotor, ShooterConfig.shooterFlywheelMotorPIDF, PancakeShooterConstants.shooterInverted[0])
        self.configureMotor(self.followerFlywheelMotor, ShooterConfig.shooterFlywheelMotorPIDF, PancakeShooterConstants.shooterInverted[1], leader=self.leadFlywheelMotor)
        self.configureMotor(self.leadFeedMotor, ShooterConfig.shooterFeedMotorPIDF, PancakeShooterConstants.shooterInverted[3])
        self.configureMotor(self.followerFeedMotor, ShooterConfig.shooterFeedMotorPIDF, PancakeShooterConstants.shooterInverted[4], leader=self.leadFeedMotor)

        self.motors: Dict[str, rev.SparkFlex | rev.SparkMax] = {
            ShooterMotorNames.LEAD_FLYWHEEL: self.leadFlywheelMotor,
            ShooterMotorNames.FOLLOWER_FLYWHEEL: self.followerFlywheelMotor,
            ShooterMotorNames.LEAD_FEED: self.leadFeedMotor,
            ShooterMotorNames.FOLLOWER_FEED: self.followerFeedMotor
        }

        # Get encoders from each motor to read data
        self.leadFlywheelEncoder = self.leadFlywheelMotor.getEncoder()
        self.followerFlywheelEncoder = self.followerFlywheelMotor.getEncoder()
        self.leadFeedEncoder = self.leadFeedMotor.getEncoder()
        self.followerFeedEncoder = self.followerFeedMotor.getEncoder()
        self.encoders = {
            ShooterMotorNames.LEAD_FLYWHEEL: self.leadFlywheelEncoder,
            ShooterMotorNames.FOLLOWER_FLYWHEEL: self.followerFlywheelEncoder,
            ShooterMotorNames.LEAD_FEED: self.leadFeedEncoder,
            ShooterMotorNames.FOLLOWER_FEED: self.followerFeedEncoder,
        }

        # Create closed loop controllers to be able to set a reference/goal for pid
        self.leadFlywheelPID = self.leadFlywheelMotor.getClosedLoopController()
        self.leadFeedPID = self.leadFeedMotor.getClosedLoopController()
        self.PIDs = {
            ShooterMotorNames.LEAD_FLYWHEEL: self.leadFlywheelPID,
            ShooterMotorNames.LEAD_FEED: self.leadFeedPID,
            # Avoid key errors
            ShooterMotorNames.FOLLOWER_FLYWHEEL: self.leadFlywheelPID,
            ShooterMotorNames.FOLLOWER_FEED: self.leadFeedPID
        }

    def configureMotor(
        self, motor: rev.SparkFlex | rev.SparkMax,
        pidf: tuple,
        invert: bool,
        positionConversionFactor: float = None,
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

        if positionConversionFactor is not None:
            configs.encoder.positionConversionFactor(positionConversionFactor)

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

    def setMotorReference(self, motorName: str, setpoint: float, controlType: rev.SparkLowLevel.ControlType):
        """
        Give a custom setpoint for PID to achieve

        Args:
            motorName: Name of the motor
            setpoint: The PID setpoint for the target motor

        Returns:
            None
        """
        self.PIDs[motorName].setReference(setpoint, controlType, rev.ClosedLoopSlot.kSlot0)

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

    def getPosition(self, motorName: str):
        return self.encoders[motorName].getPosition()

    def _getActiveTableArrays(self):
        """Return (distances, rpms, angles) arrays for the active target mode."""
        if self.targetMode == TargetMode.AIR:
            return self.airDistances, self.airRpms, self.airAngles
        return self.groundDistances, self.groundRpms, self.groundAngles

    def setRpmUsingLookup(self, distance: float):
        """
        Set the RPM needed to shoot the ball at a specified distance.

        Uses the active target mode (air/ground) lookup table.

        Args:
            distance: distance in meters from a target point

        Returns:
            None
        """
        self.targetDistance = distance
        distances, rpms, _ = self._getActiveTableArrays()
        self.RPM = float(np.interp(distance, distances, rpms))

    def getHoodAngleForDistance(self, distance: float) -> float:
        """
        Get the hood angle needed to shoot at a specified distance.

        Uses the active target mode (air/ground) lookup table.

        Args:
            distance: distance in meters from a target point

        Returns:
            Hood angle in degrees
        """
        distances, _, angles = self._getActiveTableArrays()
        return float(np.interp(distance, distances, angles))

    def setRpmAtFixedPosition(self):
        """
        Set the RPM based on the designated fixed position on the field
        """
        self.RPM = self.lookupFixedPositionRPMs.get(self.fixedRPMPosition, 0)

    def cycleFixedShootingPosition(self):
        if self.fixedRPMPosition == FixedShootingPositions.DEFAULT:
            self.fixedRPMPosition = FixedShootingPositions.HUB
        elif self.fixedRPMPosition == FixedShootingPositions.HUB:
            self.fixedRPMPosition = FixedShootingPositions.TOWER
        elif self.fixedRPMPosition == FixedShootingPositions.TOWER:
            self.fixedRPMPosition = FixedShootingPositions.ALLIANCE_CORNER
        elif self.fixedRPMPosition == FixedShootingPositions.ALLIANCE_CORNER:
            self.fixedRPMPosition = FixedShootingPositions.CLOSE_FEED
        elif self.fixedRPMPosition == FixedShootingPositions.CLOSE_FEED:
            self.fixedRPMPosition = FixedShootingPositions.MID_FEED
        elif self.fixedRPMPosition == FixedShootingPositions.MID_FEED:
            self.fixedRPMPosition = FixedShootingPositions.FAR_FEED
        elif self.fixedRPMPosition == FixedShootingPositions.FAR_FEED:
            self.fixedRPMPosition = FixedShootingPositions.DEFAULT

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

    def setTargetMode(self, mode: TargetMode):
        self.targetMode = mode

    def getTargetMode(self) -> TargetMode:
        return self.targetMode

    def toggleFlywheelActive(self):
        self.flywheelActive = not self.flywheelActive

    def toggleFeedActive(self):
        self.feedActive = not self.feedActive

    def calculateRangeFromOdometry(
        self,
        odometry: Callable[[],Pose2d],
        targetLocation: Callable[[],Translation2d]
    ):
        return abs(odometry().translation().distance(targetLocation()))

    def periodic(self):
        newRPM = self.RPM + self.offsetAmount
        if self.feedActive:
            feedRPM = int(newRPM * PancakeShooterConstants.shooterFeedPercentOfFlywheel)
            self.setMotorReference(ShooterMotorNames.LEAD_FEED, feedRPM, rev.SparkLowLevel.ControlType.kVelocity)
        else:
            feedRPM = 0
            self.setMotorVoltage(ShooterMotorNames.LEAD_FEED, 0)

        if self.flywheelActive:
            self.setMotorReference(ShooterMotorNames.LEAD_FLYWHEEL, newRPM, rev.SparkLowLevel.ControlType.kVelocity)
        else:
            newRPM = 0
            self.setMotorVoltage(ShooterMotorNames.LEAD_FLYWHEEL, 0)

        wpilib.SmartDashboard.putNumber("Shooter_RPM", newRPM)
        wpilib.SmartDashboard.putNumber("Shooter_Feed_RPM", feedRPM)
        wpilib.SmartDashboard.putNumber("Shooter_Offset", self.offsetAmount)
        wpilib.SmartDashboard.putNumber("Shooter_Offset_Delta", self.offsetDelta)
        wpilib.SmartDashboard.putBoolean("Shooter_Feed_Active", self.feedActive)
        wpilib.SmartDashboard.putBoolean("Shooter_Flywheel_Active", self.flywheelActive)
        wpilib.SmartDashboard.putString("Shooter_Flywheel_Mode", self.flywheelMode)
        wpilib.SmartDashboard.putString("Shooter_Fixed_RPM_Position", self.fixedRPMPosition)
        wpilib.SmartDashboard.putNumber("Shooter_Target_Distance", self.targetDistance)
        wpilib.SmartDashboard.putString("Shooter_Target_Mode", self.targetMode)
        wpilib.SmartDashboard.putNumber("Shooter_Hood_Angle", self.getHoodAngleForDistance(self.targetDistance))
