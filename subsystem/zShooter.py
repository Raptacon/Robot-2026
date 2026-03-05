from config import OperatorRobotConfig
import rev
from typing import Dict
from math import sqrt
from math import floor

class zShooter():
    def __init__(self):
        super().__init__()
        self.robotConfigs = OperatorRobotConfig()
        self.configs = rev.SparkBaseConfig()

        self.offsetAmount = 0

        # Create lookup table of 100 elements (index 0-99)
        self.lookupTable = ([1000]*25) + ([2000]*25) + ([3000]*25) + ([4000]*25)

        # Instantiate motors
        # TODO: set a f
        self.feedMotor = rev.SparkFlex(30, rev.SparkLowLevel.MotorType.kBrushless)
        self.leadFlywheelMotor = rev.SparkFlex(10, rev.SparkLowLevel.MotorType.kBrushless)
        self.followerFlywheelMotor = rev.SparkMax(6, rev.SparkLowLevel.MotorType.kBrushless)
        self.motors: Dict[str, rev.SparkFlex | rev.SparkMax] = {
            'feed': self.feedMotor,
            'lead': self.leadFlywheelMotor,
            'follower': self.followerFlywheelMotor
        }

        # Get encoders from each motor to read data
        self.feedEncoder = self.feedMotor.getEncoder()
        self.leadFlywheelEncoder = self.leadFlywheelMotor.getEncoder()
        self.followerFlywheelEncoder = self.followerFlywheelMotor.getEncoder()
        self.encoders = {
            'feed': self.feedEncoder,
            'lead': self.leadFlywheelEncoder,
            'follower': self.followerFlywheelEncoder
        }

        # Create closed loop controllers to be able to set a reference/goal for pid
        self.feedPID = self.feedMotor.getClosedLoopController()
        self.leadFlywheelPID = self.leadFlywheelMotor.getClosedLoopController()
        self.followerFlywheelPID = self.followerFlywheelMotor.getClosedLoopController()
        self.PIDs = {
            'feed': self.feedPID,
            'lead': self.leadFlywheelPID,
            'follower': self.followerFlywheelPID
        }

        # Set up configs for each motor
        # Check if motors should be inverted
        # Create method to combine PIDF values and inverted
        self.configs.closedLoop.pidf(*self.robotConfigs.shooterFeedMotorPIDF, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.shooterInverted[0])
        self.feedMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)
        
        self.configs.closedLoop.pidf(*self.robotConfigs.shooterLeadMotorPIDF, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.shooterInverted[0])
        self.leadFlywheelMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)
        
        self.configs.closedLoop.pidf(*self.robotConfigs.shooterFollowerMotorPIDF, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.shooterInverted[0])
        self.followerFlywheelMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)

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

    def setAllMotorReferences(self, rpm: float):
        """
        Give a custom setpoint for PID to achieve in terms of velocity and apply to all
        motors on the shooter

        Args:
            rpm: The velocity setpoint for the motor in RPM

        Returns:
            None
        """
        for motorName in self.PIDs:
            self.setMotorReference(motorName=motorName, rpm=rpm)

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
            newRPM = max([-(a) + sqrt(discriminant) / (2*b), -(a) - sqrt(discriminant) / (2*b)] )
            self.RPM = newRPM + self.offsetAmount

    # def calculate_RPM(self, a, b, c, d, distance, angle):
    #     self.angle = -(a) + sqrt(a**2 - ((4*b)*(c*angle + d*angle**2)) + 4*b*distance ) / 2*b
    #     return self.angle

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
            self.RPM = self.lookupTable[lookupIndex] + self.offsetAmount
        else:
            if len(self.lookupTable) > 0:
                self.RPM = self.lookupTable[-1] + self.offsetAmount
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
        self.setMotorReference('feed', self.RPM)
        self.setMotorReference('lead', self.RPM)
        self.setMotorReference('follower', self.RPM)
