from config import OperatorRobotConfig
import rev
import wpilib
from commands2 import Subsystem
from typing import Dict
from math import floor, sqrt
from enum import StrEnum


class ShooterMotorNames(StrEnum):
    """
    Create consistent names for shooter motor references
    """

    FEED = "feed"
    LEAD_FLYWHEEL = "lead"
    FOLLOWER_FLYWHEEL = "follower"


class zShooter(Subsystem):
    def __init__(self):
        super().__init__()
        self.robotConfigs = OperatorRobotConfig()

        self.offsetAmount = 0

        # Create lookup table of 100 elements (index 0-99)
        self.lookupTable = ([1000]*25) + ([2000]*25) + ([3000]*25) + ([4000]*25)

        # Instantiate motors
        self.feedMotor = rev.SparkFlex(30, rev.SparkLowLevel.MotorType.kBrushless)
        self.leadFlywheelMotor = rev.SparkFlex(32, rev.SparkLowLevel.MotorType.kBrushless)
        self.followerFlywheelMotor = rev.SparkMax(33, rev.SparkLowLevel.MotorType.kBrushless)

        # Set up configs for each motor
        self.configureMotor(self.feedMotor, self.robotConfigs.shooterFeedMotorPIDF, self.robotConfigs.shooterInverted[0])
        self.configureMotor(self.leadFlywheelMotor, self.robotConfigs.shooterFlywheelMotorPIDF, self.robotConfigs.shooterInverted[1])
        self.configureMotor(self.followerFlywheelMotor, self.robotConfigs.shooterFlywheelMotorPIDF, self.robotConfigs.shooterInverted[2], self.leadFlywheelMotor)

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

    def calculateDistance(self, a, b, c, d, RPM, angle):
        """
        Calculate the distance a ball will travel when given RPM and angle of the shooter

        Args:
            a: Some constant
            b: Some constant
            c: Some constant
            d: Some constant
            RPM: revolutions per minute of the motor
            Angle: the angle in degrees(?) that the ball exits at

        Returns:
            Distance the ball is expected to travel
        """
        self.distance = a*RPM + b*RPM**2 + c*angle + d*angle**2
        return self.distance

    def calculateRpmFromDistance(self, a, b, distance):
        """
        Calculate either the rpm needed to travel a certain distance

        Args:
            a: Some constant
            b: Some constant
            distance: the length in meters(?) the ball needs to travel

        Returns:
            None
        """
        discriminant = a**2 - (4*b*distance)
        if (not (discriminant < 0)) and (b != 0):
            self.RPM = max([-(a) + sqrt(discriminant) / (2*b), -(a) - sqrt(discriminant) / (2*b)] )

    def getLookupTable(self, distance: float):
        """
        Get the RPM needed to shoot the ball at a specified distance

        Args:
            distance: distance in meters from a target point

        Returns:
            RPM needed to hit distance target
        """
        # Get an index number from the distance given
        lookupIndex = abs(int(floor(distance / self.robotConfigs.shooterRangeInterval)))
        # Check if index number has exceeded the length of the list, else set RPM as 0
        if lookupIndex < len(self.lookupTable):
            self.RPM = self.lookupTable[lookupIndex]
        else:
            if len(self.lookupTable) > 0:
                self.RPM = self.lookupTable[-1]
            else:
                self.RPM = 0

    def increaseOffset(self):
        """
        Increase the RPM by a set amount if it is inaccurate

        Args:
            None

        Returns:
            None
        """
        self.offsetAmount = self.offsetAmount + self.robotConfigs.shooterOffsetIncrement

    def decreaseOffset(self):
        """
        Decrease the RPM by a set amount if it is inaccurate

        Args:
            None

        Returns:
            None
        """
        self.offsetAmount = self.offsetAmount + self.robotConfigs.shooterOffsetDecrement

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

    def periodic(self):
        newRPM = self.RPM + self.offsetAmount
        feedRPM = int(newRPM * self.robotConfigs.shooterFeedPercentOfFlywheel)

        self.setMotorReference(ShooterMotorNames.FEED, feedRPM)
        self.setMotorReference(ShooterMotorNames.LEAD_FLYWHEEL, newRPM)

        wpilib.SmartDashboard.putNumber("Shooter_RPM", newRPM)
        wpilib.SmartDashboard.putNumber("Shooter_Feed_RPM", feedRPM)
        wpilib.SmartDashboard.putNumber("Shooter_Offset", self.offsetAmount)
