import wpilib
import commands2
import rev
import time
import array

from constants import IntakePivotConstants as intakeConsts


class IntakeSubsystem(commands2.Subsystem):
    def __init__(self):
        super().__init__()
        self.pivotMotor = rev.SparkFlex(intakeConsts.canId, rev.SparkLowLevel.MotorType.kBrushless)
        self.pivotMotorEncoder = self.pivotMotor.getEncoder()
        self.pivotMotorConfig = rev.SparkMaxConfig()
        self.pivotMotorEncoder.setPosition(0)

        #Set Variables
        self.pivotDeployed = 155
        self.pivotStowed = 0
        self.pivotFaultThreshold = 2
        self.pivotBaseSpeed = 0.3

        # Motor setpoints: the value passed directly to motor.set() each cycle
        self.pivotSetpoint = 0.0
        self.rampPower = 0.0

        self.pivotRampComplete = False
        self.pivotRamping = False
        self.baselineFault = 0.0
        self.pivotDifference = 0.0
        self.remainingRotations = 0.0
        self.pivotSlowdownPosition = 0.0
        self.pivotRamp = 0.0
        self.pivotMotorPositions = array.array('f', [0, 0, 0, 0, 0])

    def deployIntake(self):
        if self.pivotSetpoint <= 0 and self.pivotMotorEncoder.getPosition() <= self.pivotDeployed:
            self.baselineFault = time.perf_counter()
            self.pivotSetpoint = self.pivotBaseSpeed
        if self.pivotSetpoint >= 0:
            if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
                self.pivotSetpoint = 0
            if self.baselineFault - time.perf_counter() >= self.pivotFaultThreshold:
                wpilib.Alert("INTAKE ERR101: Deployment of intake doesn't appear to be working! Stopped activation.", wpilib.Alert.AlertType.kError)
                return
        else:
            self.pivotSetpoint = 0

    def isIntakeDeployed(self) -> bool:
        """True when Intake is deployed"""
        return self.pivotMotorEncoder.getPosition() >= self.pivotDeployed

    def isIntakeStowed(self) -> bool:
        """True when Intake is stowed"""
        return self.pivotMotorEncoder.getPosition() <= self.pivotStowed

    def stowIntake(self):
        if self.pivotSetpoint >= 0 and self.pivotMotorEncoder.getPosition() >= self.pivotStowed:
            self.baselineFault = time.perf_counter()
            self.pivotSetpoint = -self.pivotBaseSpeed
        if self.pivotSetpoint <= 0:
            if self.pivotMotorEncoder.getPosition() <= self.pivotStowed:
                self.pivotSetpoint = 0
            if self.baselineFault - time.perf_counter() >= self.pivotFaultThreshold:
                wpilib.Alert("INTAKE ERR112: Intake Stow doesn't appear to be working! Stopping activation.", wpilib.Alert.AlertType.kError)
                return
        else:
            self.pivotSetpoint = 0

    def pivotSlowdown(self):
        self.pivotDifference = abs(self.pivotStowed) + abs(self.pivotDeployed)
        if self.pivotSetpoint == self.pivotBaseSpeed:
            self.remainingRotations = self.pivotDifference - (abs(self.pivotStowed) + abs(0 - self.pivotMotorEncoder.getPosition()))
            self.pivotSlowdownPosition = self.pivotStowed + (self.pivotDifference * 0.75)
            if self.pivotMotorEncoder.getPosition() >= self.pivotSlowdownPosition:
                self.pivotSetpoint = self.pivotBaseSpeed / 2
        if self.pivotSetpoint == -self.pivotBaseSpeed:
            self.remainingRotations = self.pivotDifference - (self.pivotDeployed - self.pivotMotorEncoder.getPosition() - abs(self.pivotStowed))
            self.pivotSlowdownPosition = self.pivotDeployed - (self.pivotDifference * 0.75)
            if self.pivotMotorEncoder.getPosition() <= self.pivotSlowdownPosition:
                self.pivotSetpoint = -self.pivotBaseSpeed / 2

    def rampIntake(self):
        if not self.pivotRampComplete:
            self.pivotDifference = abs(self.pivotStowed) + abs(self.pivotDeployed)
            self.pivotRamp = self.pivotStowed + (self.pivotDifference * 0.5)
            if self.pivotMotorEncoder.getPosition() <= self.pivotRamp:
                if self.rampPower <= 0:
                    self.baselineFault = time.perf_counter()
                    self.rampPower = 1
                    self.pivotSetpoint = self.pivotBaseSpeed
                    self.pivotRamping = True
            elif self.pivotMotorEncoder.getPosition() >= self.pivotRamp:
                if self.rampPower >= 0:
                    self.baselineFault = time.perf_counter()
                    self.rampPower = -1
                    self.pivotSetpoint = -self.pivotBaseSpeed
                    self.pivotRamping = True

    def motorChecks(self):
        # Check if intake deployment motor is deploying outside of limits
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed + 15 and self.pivotSetpoint >= 0:
            wpilib.Alert("INTAKE ERR122: Intake Motor appears to be deploying outside of limits! Motor has been disabled.", wpilib.Alert.AlertType.kError)
            self.pivotMotor.disable()

        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed - 15 and self.pivotSetpoint <= 0:
            wpilib.Alert("INTAKE ERR122: Intake Motor appears to be stowing outside of limits! Motor has been disabled.", wpilib.Alert.AlertType.kError)
            self.pivotMotor.disable()

        # Stop intake deployment motor if it reaches limits
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed and self.pivotSetpoint >= 0:
            self.pivotSetpoint = 0
        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed and self.pivotSetpoint <= 0:
            self.pivotSetpoint = 0

        # Stop intake deployment motor if its position does not change even when it is supposed to be moving
        self.pivotMotorPositions.pop(0)
        self.pivotMotorPositions.append(self.pivotMotorEncoder.getPosition())
        if not self.pivotMotorEncoder.getPosition() <= self.pivotStowed and not self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
            if self.pivotMotorPositions.count(self.pivotMotorEncoder.getPosition()) == 5:
                if self.pivotSetpoint < 0:
                    self.pivotStowed = self.pivotMotorEncoder.getPosition() + 1
                    self.pivotSetpoint = 0
                elif self.pivotSetpoint > 0:
                    self.pivotDeployed = self.pivotMotorEncoder.getPosition() - 1
                    self.pivotSetpoint = 0

        self.pivotMotor.set(self.pivotSetpoint)

        # Stop pivot deployment motor if it is being ramped
        if self.pivotRamping:
            if self.rampPower == 1:
                if self.pivotMotorEncoder.getPosition() >= self.pivotRamp:
                    self.rampPower = 0
                    self.pivotSetpoint = 0
                    self.pivotRampComplete = True
            if self.rampPower == -1:
                if self.pivotMotorEncoder.getPosition() <= self.pivotRamp:
                    self.rampPower = 0
                    self.pivotSetpoint = 0
                    self.pivotRampComplete = True

        # Allows pivot to be ramped even from deployed/stowed position
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
            self.rampPower = 0
        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed:
            self.rampPower = 0

        if self.pivotSetpoint != 0:
            self.pivotRampComplete = False

    def periodic(self):
        wpilib.SmartDashboard.putNumber("Intake Position", self.pivotMotorEncoder.getPosition())
        wpilib.SmartDashboard.putNumber("Intake Deployed", self.pivotDeployed)
        wpilib.SmartDashboard.putNumber("Pivot Setpoint", self.pivotSetpoint)
        wpilib.SmartDashboard.putNumber("Intake Difference", self.pivotDifference)
        wpilib.SmartDashboard.putNumber("Remaining Rotations", self.remainingRotations)
        wpilib.SmartDashboard.putNumber("Intake Slowdown Position", self.pivotSlowdownPosition)
        wpilib.SmartDashboard.putNumber("Ramp Power", self.rampPower)
        wpilib.SmartDashboard.putNumber("Intake Ramp Position", self.pivotRamp)
        wpilib.SmartDashboard.putBoolean("Intake Ramp Complete", self.pivotRampComplete)
        wpilib.SmartDashboard.putNumberArray("Intake Positions", self.pivotMotorPositions)
        wpilib.SmartDashboard.putNumber("Intake Stowed", self.pivotStowed)

        self.motorChecks()
        self.pivotSlowdown()
