import wpilib
import commands2
import rev
import time
import array

from constants import CaptainPlanetConsts as intakeConsts
from config import OperatorRobotConfig


class IntakeSubsystem(commands2.SubsystemBase):
    def __init__(self):
        #Initializes all devices
        self.pivotMotor = rev.SparkFlex(intakeConsts.kIntakeMotorCanId, rev.SparkLowLevel.MotorType.kBrushless)
        self.pivotMotorEncoder = self.pivotMotor.getEncoder()
        self.pivotMotorConfig = rev.SparkMaxConfig()
        self.pivotMotorEncoder.setPosition(0)
        # self.tuningMotors()

        self.rollerMotor = rev.SparkFlex(intakeConsts.kRollerMotorCanId, rev.SparkLowLevel.MotorType.kBrushless)
        self.rollerMotorEncoder = self.rollerMotor.getEncoder()

        # self.breakBeam = wpilib.DigitalInput(intakeConsts.kBreakBeam)
        # self.frontBreakbeam = wpilib.DigitalInput(intakeConsts.kFrontBreakBeam)
        # self.backBreakbeam = wpilib.DigitalInput(intakeConsts.kBackBreakBeam)
        # self.frontBeamBroken = not self.frontBreakbeam.get()
        # self.backBeamBroken = not self.backBreakbeam.get()

        # self.HallEffectSensor = wpilib.DigitalInput(intakeConsts.kHallEffectSensor)

        #Set Variables
        self.pivotDeployed = 155 #Minimum amount of rotations before assuming intake is deployed
        self.pivotStowed = 0 #Maximum amount of rotations before assuming intake is stowed
        self.pivotFaultThreshold = 2 #Amount of time spent trying to deploy/stow intake before fault condition is triggered
        # self.pivotMagnetFaultThreshold = 2 #Amount of time before magnets need to have stopped tripping hall effects sensor or fault condition is triggered
        self.rollerFaultThreshold = 2 #Amount of time spent trying to operate rollers before fault condition is triggered
        self.jamFaultThreshold = 0 #Amount of attempts done trying to reverse rollers in the event of a jam before a fault condition is triggered
        self.jamTime = 1 #Amount of time to wait before assuming a ball inside the intake has gotten stuck
        self.jamThreshold = 10 #Maximum sustained rpm before assuming a ball inside the rollers has gotten stuck
        self.jamReversalTime = 3 #Amount of time to have motors reverse when a ball inside the intake has gotten stuck
        self.unjam = 1500 #Minimum sustained rpm before assuming rollers have been unjammed
        self.pivotBaseSpeed = 0.3 #Base speed for pivot motor, used when setting setpoints
        self.rollerBaseSpeed = 0.3 #Base speed for roller motor, used when setting setpoints
        # RPM below which the roller is considered stopped. Accounts for
        # small rocking motion when the robot moves. Tune as needed.
        self.rollerStoppedThreshold = 0.5

        # Motor setpoints: the value passed directly to motor.set() each cycle
        # Sign determines direction, magnitude determines speed
        self.pivotSetpoint = 0.0 #Leave at 0, direct motor output for pivot
        self.rollerSetpoint = 0.0 #Leave at 0, direct motor output for roller
        self.rampPower = 0.0 #Leave at 0, tracks ramp direction: -1, 0, or 1

        self.pivotRampComplete = False #Leave at False, provides reference to code on whether ramping intake is finished
        self.pivotRamping = False #Leave at False, provides reference to code on whether intake is moving to ramp
        self.baselineFault = 0.0 #Leave at 0, provides baseline to compare to when determining faults
        self.baselineJam = 0.0 #Leave at 0, provides baseline to compare to when determining faults
        self.jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered
        self.pivotDifference = 0.0 #Leave at 0, rotations required to get from intake stowed position to intake deployed position is automatically calculated
        self.remainingRotations = 0.0 #Leave at 0, rotations remaining to finish deploying/stowing intake is automatically calculated
        self.pivotSlowdownPosition = 0.0 #Leave at 0, stores amount of intake motor rotations required to slow it down
        self.pivotRamp = 0.0 #Leave at 0, motor position for ramp is automatically calculated
        self.hardStopIndex = 0 #Leave at 0, provides index to code for hardstop checks
        self.jamTimingActive = False #Leave at False, whether jam timing window is active
        self.baselineDetectedJam = 0.0 #Leave at 0, provides baseline to compare to when jam detection is activated
        self.rollerStoppedOnce = False #Leave at False, ensures that the rollers are stopped only once, preventing obstruction of manual controls

        self.jamDetected = False #Leave at False
        self.pivotMotorPositions = array.array('f', [0, 0, 0, 0, 0]) #Leave with all zeros, for checking if intake motor stopped during deployment/stowing

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

    def requestRollerOn(self):
        """Request roller spin-up. motorChecks() in periodic() drives the motor."""
        self.rollerSetpoint = self.rollerBaseSpeed
        self.rollerStoppedOnce = False
        self.baselineFault = time.perf_counter()

    def requestRollerOff(self):
        """Request roller spin-down. motorChecks() in periodic() drives the motor."""
        self.rollerSetpoint = 0
        self.baselineFault = time.perf_counter()

    def isRollerOn(self) -> bool:
        """True when roller is commanded on AND actually spinning."""
        return self.rollerSetpoint != 0 and abs(self.rollerMotorEncoder.getVelocity()) > self.rollerStoppedThreshold

    def isRollerOff(self) -> bool:
        """True when roller velocity is below the stopped threshold."""
        return abs(self.rollerMotorEncoder.getVelocity()) <= self.rollerStoppedThreshold
    
    def isIntakeDeployed(self) -> bool:
        """True when Intake is deployed"""
        return self.pivotMotorEncoder.getPosition() >= self.pivotDeployed
    
    def isIntakeStowed(self) -> bool:
        """True when Intake is stowed"""
        return self.pivotMotorEncoder.getPosition() <= self.pivotStowed
    
    def toggleIntakeDeployment(self) -> bool:
        """Toggles between Intake Deployment and stow; If intake is deployed, stow it, and vice versa."""
        if self.isIntakeStowed():
            self.deployIntake()
        if self.isIntakeDeployed():
            self.stowIntake()

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

    def jamDetection(self):
        if not self.jamDetected:
            self.rollerStoppedOnce = False
            if self.rollerSetpoint > 0:
                if self.rollerMotorEncoder.getVelocity() <= self.jamThreshold:
                    if not self.jamTimingActive:
                        self.baselineJam = time.perf_counter()
                        self.jamTimingActive = True
                    else:
                        if time.perf_counter() - self.baselineJam >= self.jamTime:
                            self.baselineDetectedJam = time.perf_counter()
                            self.jamDetected = True
                else:
                    self.jamTimingActive = False
        else:
            if time.perf_counter() - self.baselineDetectedJam <= self.jamReversalTime and self.jamTimingActive:
                self.rollerSetpoint = -self.rollerBaseSpeed
                if abs(self.rollerMotorEncoder.getVelocity()) >= self.unjam:
                    self.jamTimingActive = False
            else:
                if self.rollerMotorEncoder.getVelocity() <= self.unjam:
                    wpilib.Alert("Jam reversal unsuccessful! Stopping motor.", wpilib.Alert.AlertType.kError)
                    self.rollerMotor.disable()
                if not self.rollerStoppedOnce:
                    self.requestRollerOff()
                    self.rollerStoppedOnce = True
                else:
                    self.rollerSetpoint = self.rollerBaseSpeed
                    self.jamTimingActive = False
                    self.jamDetected = False

    # def automaticRollerActivation(self):
        # if not self.breakBeam.get():
        #     self.rollerStoppedOnce = True
        #     self.requestRollerOn()
        # else:
        #     if self.rollerStoppedOnce:
        #         self.requestRollerOff()
        #         self.rollerStoppedOnce = False

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
        # Check if intake deployment motor is deploying without limits
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

        self.rollerMotor.set(self.rollerSetpoint)

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

    def tuningMotors(self):
        (
            self.pivotMotorConfig.closedLoop
            .setFeedbackSensor(rev.FeedbackSensor.kPrimaryEncoder)
            .pidf(*OperatorRobotConfig.intake_pivot_pid)
        )

        (
            self.pivotMotorConfig.encoder
            .velocityConversionFactor(18)
        )

        self.pivotMotor.configure(
            self.pivotMotorConfig, rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kPersistParameters
        )

        self.pivotMotorPID = self.pivotMotor.getClosedLoopController()
        self.state_speed = 0


    def periodic(self):
        wpilib.SmartDashboard.putNumber("Intake Position", self.pivotMotorEncoder.getPosition())
        wpilib.SmartDashboard.putNumber("Roller Position", self.rollerMotorEncoder.getPosition())
        wpilib.SmartDashboard.putNumber("Intake Deployed", self.pivotDeployed)
        # wpilib.SmartDashboard.putBoolean("Hall Effects Sensor", self.HallEffectSensor.get())
        wpilib.SmartDashboard.putNumber("Time", time.perf_counter())
        wpilib.SmartDashboard.putNumber("Baseline Fault", self.baselineFault)
        wpilib.SmartDashboard.putNumber("Pivot Setpoint", self.pivotSetpoint)
        wpilib.SmartDashboard.putBoolean("Roller Stopped Once", self.rollerStoppedOnce)
        wpilib.SmartDashboard.putNumber("Intake Difference", self.pivotDifference)
        wpilib.SmartDashboard.putNumber("Remaining Rotations", self.remainingRotations)
        wpilib.SmartDashboard.putNumber("Intake Slowdown Position", self.pivotSlowdownPosition)
        wpilib.SmartDashboard.putNumber("Ramp Power", self.rampPower)
        wpilib.SmartDashboard.putNumber("Intake Ramp Position", self.pivotRamp)
        wpilib.SmartDashboard.putBoolean("Intake Ramp Complete", self.pivotRampComplete)
        wpilib.SmartDashboard.putNumberArray("Intake Positions", self.pivotMotorPositions)
        wpilib.SmartDashboard.putNumber("Intake Stowed", self.pivotStowed)
        wpilib.SmartDashboard.putNumber("Roller Setpoint", self.rollerSetpoint)
        wpilib.SmartDashboard.putBoolean("Roller Jam", self.jamDetected)
        wpilib.SmartDashboard.putNumber("Actual Roller Velocity", self.rollerMotorEncoder.getVelocity())
        wpilib.SmartDashboard.putNumber("Baseline Detected Jam", self.baselineDetectedJam)
        wpilib.SmartDashboard.putNumber("Pivot Motor Output", self.pivotSetpoint)
        wpilib.SmartDashboard.putNumber("Baseline Jam", self.baselineJam)

        self.motorChecks()
        # self.automaticRollerActivation()
        self.pivotSlowdown()
        self.jamDetection()
