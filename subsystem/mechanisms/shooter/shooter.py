# Native imports
import numpy as np
from enum import StrEnum

# Internal imports
from config import ShooterConfig
from constants.swerve_constants import ShooterConstants
from utils.spark_utils import GetSparkSignalsPositionControlConfig

# Third-party imports
from commands2 import Subsystem
import rev
import wpilib


class TargetMode(StrEnum):
    """Target profile for distance-based RPM and hood angle lookup."""
    AIR = "air"
    GROUND = "ground"


class Shooter(Subsystem):
    """Flywheel shooter — controls only the two flywheel motors.

    Two operating modes (setRange takes priority over setRPM):
      - setRPM(rpm): direct RPM control, used for manual/fixed shooting
      - setRange(distance): calculates RPM and hood angle from lookup table

    Feed motors are managed by the separate Feed subsystem.
    """

    def __init__(self):
        super().__init__()
        self.offsetAmount = 0
        self.targetRPM = 0
        self._range_rpm = None  # When set, takes priority over targetRPM
        self._range_distance = 0.0
        self._range_hood_angle = 0.0
        self.targetMode = TargetMode.AIR
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
            # Follower: slow down all frames — we don't read from it
            (
                configs.signals
                .primaryEncoderVelocityPeriodMs(500)
                .primaryEncoderPositionPeriodMs(500)
                .appliedOutputPeriodMs(500)
                .busVoltagePeriodMs(500)
                .outputCurrentPeriodMs(500)
                .motorTemperaturePeriodMs(500)
            )
        else:
            configs.inverted(invert)
            configs.closedLoop.pidf(*pidf, rev.ClosedLoopSlot.kSlot0)
            # Leader: fast velocity for PID, plus telemetry
            GetSparkSignalsPositionControlConfig(configs.signals, 20)
        motor.configure(
            configs,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kPersistParameters,
        )

    # -- Public API --

    def setRPM(self, rpm: float):
        """Set flywheel RPM directly. Cleared if setRange() is called."""
        self._range_rpm = None
        self.targetRPM = rpm

    def setRange(self, distance: float):
        """Set RPM and hood angle from distance lookup. Takes priority over setRPM.

        TODO: Add overload that accepts robot Pose2d and target Translation2d,
        computes distance internally, so callers don't need to do the math.
        """
        self._range_distance = distance
        distances, rpms, angles = self._getActiveTableArrays()
        self._range_rpm = float(np.interp(distance, distances, rpms))
        self._range_hood_angle = float(np.interp(distance, distances, angles))

    def clearRange(self):
        """Clear range mode, revert to direct RPM control."""
        self._range_rpm = None

    def getEffectiveRPM(self) -> float:
        """Return the RPM that will be commanded (range or direct + offset)."""
        base = self._range_rpm if self._range_rpm is not None else self.targetRPM
        return base + self.offsetAmount

    def getHoodAngle(self) -> float:
        """Return hood angle — from range lookup or 0 if in direct RPM mode."""
        return self._range_hood_angle if self._range_rpm is not None else 0.0

    def getVelocity(self) -> float:
        """Get the current flywheel velocity in RPM."""
        return self.leadEncoder.getVelocity()

    def toggleFlywheelActive(self):
        self.flywheelActive = not self.flywheelActive

    def modifyOffset(self, offsetDelta: float):
        self.offsetAmount += offsetDelta

    def resetOffset(self):
        self.offsetAmount = 0

    def setTargetMode(self, mode: TargetMode):
        self.targetMode = mode

    def getTargetMode(self) -> TargetMode:
        return self.targetMode

    def _getActiveTableArrays(self):
        if self.targetMode == TargetMode.AIR:
            return self.airDistances, self.airRpms, self.airAngles
        return self.groundDistances, self.groundRpms, self.groundAngles

    # -- Periodic --

    def periodic(self):
        effectiveRPM = self.getEffectiveRPM()

        if self.flywheelActive:
            self.leadPID.setReference(
                effectiveRPM,
                rev.SparkLowLevel.ControlType.kVelocity,
                rev.ClosedLoopSlot.kSlot0,
            )
        else:
            effectiveRPM = 0
            self.leadMotor.setVoltage(0)

        sd = wpilib.SmartDashboard
        sd.putNumber("Shooter_RPM", effectiveRPM)
        sd.putNumber("Shooter_Offset", self.offsetAmount)
        sd.putBoolean("Shooter_Flywheel_Active", self.flywheelActive)
        sd.putNumber("Shooter_Range_Distance", self._range_distance)
        sd.putNumber("Shooter_Hood_Angle", self.getHoodAngle())
        sd.putNumber("Shooter_Velocity", self.leadEncoder.getVelocity())
        sd.putBoolean("Shooter_Range_Mode", self._range_rpm is not None)
