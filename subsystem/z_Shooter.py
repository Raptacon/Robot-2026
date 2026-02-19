import commands2
from config import OperatorRobotConfig
import rev
from typing import Dict
import wpilib

class zShooter():
    def __init__(self):
        super().__init__()
        self.robotConfigs = OperatorRobotConfig()
        self.configs = rev.SparkBaseConfig()

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
        self.configs.closedLoop.pidf(*self.robotConfigs.intake_motor_pidf, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.inverted[0])
        self.intakeMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)
        
        self.configs.closedLoop.pidf(*self.robotConfigs.top_motor_pidf, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.inverted[0])
        self.topMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)
        
        self.configs.closedLoop.pidf(*self.robotConfigs.bottom_motor_pidf, rev.ClosedLoopSlot.kSlot0)
        self.configs.inverted(self.robotConfigs.inverted[0])
        self.bottomMotor.configure(self.configs, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kPersistParameters)

    # def setIntakeSpeed(self, volts):
    #     self.intakeMotor.setVoltage(volts)
    # def setTopShooterSpeed(self, volts):
    #     self.topMotor.setVoltage(volts)
    # def setBottomShooterSpeed(self, volts):
    #     self.bottomMotor.setVoltage(volts)

    def setMotorSpeed(self, motorName: str, volts: float):
        self.motors[motorName].setVoltage(volts)

    def setMotorReference(self, motorName: str, rpm: int):
        self.PIDs[motorName].setReference(rpm, rev.SparkLowLevel.ControlType.kVelocity, rev.ClosedLoopSlot.kSlot0)