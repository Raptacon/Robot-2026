import commands2
from config import OperatorRobotConfig
import rev
from typing import Dict
import wpilib
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
        self.intakeMotor = rev.SparkFlex(14, rev.SparkLowLevel.MotorType.kBrushless)
        self.topMotor = rev.SparkFlex(10, rev.SparkLowLevel.MotorType.kBrushless)
        self.bottomMotor = rev.SparkMax(6, rev.SparkLowLevel.MotorType.kBrushless)
        self.motors: Dict[str, rev.SparkFlex | rev.SparkMax] = {
            'intake': self.intakeMotor,
            'top': self.topMotor,
            'bottom': self.bottomMotor
        }

        # Get encoders from each motor to read data
        self.intakeEncoder = self.intakeMotor.getEncoder()
        self.topEncoder = self.topMotor.getEncoder()
        self.bottomEncoder = self.bottomMotor.getEncoder()
        self.encoders = {
            'intake': self.intakeEncoder,
            'top': self.topEncoder,
            'bottom': self.bottomEncoder
        }

        # Create closed loop controllers to be able to set a reference/goal for pid
        self.intakePID = self.intakeMotor.getClosedLoopController()
        self.topPID = self.topMotor.getClosedLoopController()
        self.bottomPID = self.bottomMotor.getClosedLoopController()
        self.PIDs = {
            'intake': self.intakePID,
            'top': self.topPID,
            'bottom': self.bottomPID
        }

        # Set up configs for each motor
        # Change k.NoPersistParameters to k.PersistParameters when done tuning
        self.configs.closedLoop.pidf(*self.robotConfigs.intake_motor_pidf, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.inverted[0])
        self.intakeMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        
        self.configs.closedLoop.pidf(*self.robotConfigs.top_motor_pidf, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.inverted[0])
        self.topMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        
        self.configs.closedLoop.pidf(*self.robotConfigs.bottom_motor_pidf, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.inverted[0])
        self.bottomMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)

    def setMotorVoltage(self, motorName: str, voltage: float):
        """
        Sets the voltage of the motor
        
        Args: 
            motorName: Name of the motor to set a voltage for (ie: 'intake')
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

    def calculate_rpm_or_angle_from_distance(self, a, b, distance):
        """
        Calculate either the rpm or angle needed to travel a certain distance
        
        Args:
            a: Some constant
            b: Some constant
            distance: the length in meters(?) the ball needs to travel
        
        Returns:
            RPM or angle the ball needs to be at to travel a certain distance
        """
        self.inputs = -(a) + sqrt(a**2 - 4(a)(distance)) / 2*b
        return self.inputs + self.offsetAmount

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
        lookupIndex = abs(int(floor(distance / self.robotConfigs.rangeInterval)))
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
        self.offsetAmount = self.offsetAmount + self.robotConfigs.offsetIncrement

    def decreaseOffset(self):
        """
        Decrease the RPM by a set amount if it is inaccurate
        
        Args:
            None
        
        Returns:
            None
        """
        self.offsetAmount = self.offsetAmount + self.robotConfigs.offsetDecrement

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