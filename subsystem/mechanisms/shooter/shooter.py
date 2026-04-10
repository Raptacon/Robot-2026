# Native imports
from enum import StrEnum
import numpy as np
from typing import Callable

# Internal imports
from config import ShooterConfig
from constants.swerve_constants import ShooterConstants

# Third-party imports
from commands2 import Subsystem
import rev
import wpilib
from wpimath.geometry import Pose2d, Translation2d

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
    """Flywheel shooter — controls only the two flywheel motors.

    Feed motors are managed by the separate Feed subsystem.
    """

    def __init__(self):
        super().__init__()
        self.offsetAmount = 0
        self.offsetDelta = 0
        self.targetRPM = 0
        self.targetDistance = 0.0
        self.flywheelMode = FlywheelModes.FIXED_RPM
        self.targetMode = TargetMode.AIR
        self.fixedRPMPosition = FixedShootingPositions.DEFAULT
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

        # Flywheel motors
        self.leadMotor = rev.SparkFlex(
            ShooterConstants.flywheelLeadMotorId,
            rev.SparkLowLevel.MotorType.kBrushless,
        )
        self.followerMotor = rev.SparkFlex(
            ShooterConstants.flywheelFollowerMotorId,
            rev.SparkLowLevel.MotorType.kBrushless,
        )

        self._configureMotor(
            self.leadMotor,
            ShooterConfig.shooterFlywheelMotorPIDF,
            ShooterConstants.flywheelLeadInverted,
        )
        self._configureMotor(
            self.followerMotor,
            ShooterConfig.shooterFlywheelMotorPIDF,
            ShooterConstants.flywheelFollowerInverted,
            leader=self.leadMotor,
        )

        self.leadEncoder = self.leadMotor.getEncoder()
        self.leadPID = self.leadMotor.getClosedLoopController()

    @staticmethod
    def _configureMotor(motor, pidf, invert, leader=None):
        configs = rev.SparkBaseConfig()
        configs.setIdleMode(rev.SparkBaseConfig.IdleMode.kCoast)
        configs.voltageCompensation(12.0)
        configs.smartCurrentLimit(ShooterConstants.currentLimitAmps)
        if leader is not None:
            configs.follow(leader=leader, invert=invert)
        else:
            configs.inverted(invert)
            configs.closedLoop.pidf(*pidf, rev.ClosedLoopSlot.kSlot0)
        motor.configure(
            configs,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kPersistParameters,
        )

    def setRPM(self, rpm: float):
        """
        Directly set the RPM using the given value

        Args:
            rpm: The velocity setpoint for the motor in RPM

        Returns:
            None
        """
        self.targetRPM = rpm

    def getVelocity(self) -> float:
        """Get the current flywheel velocity in RPM."""
        return self.leadEncoder.getVelocity()

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
        self.targetRPM = float(np.interp(distance, distances, rpms))

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
        self.targetRPM = self.lookupFixedPositionRPMs.get(self.fixedRPMPosition, 0)

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

    def getEffectiveRPM(self) -> float:
        """Return RPM + offset, useful for other subsystems (e.g. Feed)."""
        return self.targetRPM + self.offsetAmount

    def calculateRangeFromOdometry(
        self,
        odometry: Callable[[],Pose2d],
        targetLocation: Callable[[],Translation2d]
    ):
        return abs(odometry().translation().distance(targetLocation()))

    def periodic(self):
        newRPM = self.targetRPM + self.offsetAmount

        if self.flywheelActive:
            self.leadPID.setReference(
                newRPM,
                rev.SparkLowLevel.ControlType.kVelocity,
                rev.ClosedLoopSlot.kSlot0,
            )
        else:
            newRPM = 0
            self.leadMotor.setVoltage(0)

        wpilib.SmartDashboard.putNumber("Shooter_RPM", newRPM)
        wpilib.SmartDashboard.putNumber("Shooter_Offset", self.offsetAmount)
        wpilib.SmartDashboard.putNumber("Shooter_Offset_Delta", self.offsetDelta)
        wpilib.SmartDashboard.putBoolean("Shooter_Flywheel_Active", self.flywheelActive)
        wpilib.SmartDashboard.putString("Shooter_Flywheel_Mode", self.flywheelMode)
        wpilib.SmartDashboard.putString("Shooter_Fixed_RPM_Position", self.fixedRPMPosition)
        wpilib.SmartDashboard.putNumber("Shooter_Target_Distance", self.targetDistance)
        wpilib.SmartDashboard.putString("Shooter_Target_Mode", self.targetMode)
        wpilib.SmartDashboard.putNumber("Shooter_Hood_Angle", self.getHoodAngleForDistance(self.targetDistance))
        wpilib.SmartDashboard.putNumber("Shooter_Velocity", self.leadEncoder.getVelocity())
