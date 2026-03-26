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
        self.pivotSpeed = 0.3 #Base speed for pivot motor
        self.rollerSpeed = 0.3 #Base speed for roller motor
        # RPM below which the roller is considered stopped. Accounts for
        # small rocking motion when the robot moves. Tune as needed.
        self.rollerStoppedThreshold = 0.5

        # Motor power multipliers: sign = direction, magnitude = speed fraction
        # pivot: -1 stow, -0.5 slow stow, 0 stop, 0.5 slow deploy, 1 deploy
        # roller: -1 reverse (unjam), 0 off, 1 forward
        self.pivotPower = 0.0
        self.rollerPower = 0.0
        self.rampPower = 0.0  # pivot ramp direction multiplier

        self.pivotRampComplete = False
        self.pivotRamping = False
        self.baselineFault = 0.0
        self.baselineJam = 0.0
        self.jamReversalCount = 0
        self.pivotDifference = 0.0
        self.remainingRotations = 0.0
        self.pivotSlowdownPosition = 0.0
        self.pivotRamp = 0.0
        self.hardStopIndex = 0
        self.jamTimingActive = False
        self.baselineDetectedJam = 0.0
        self.rollerStoppedOnce = False

        self.jamDetected = False
        self.pivotMotorPositions = array.array('f', [0, 0, 0, 0, 0])

    def deployIntake(self):
        if self.pivotPower <= 0 and self.pivotMotorEncoder.getPosition() <= self.pivotDeployed:
            self.baselineFault = time.perf_counter()
            self.pivotPower = 1
        if self.pivotPower >= 0:
            if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
                self.pivotPower = 0
            if self.baselineFault - time.perf_counter() >= self.pivotFaultThreshold:
                wpilib.Alert("INTAKE ERR101: Deployment of intake doesn't appear to be working! Stopped activation.", wpilib.Alert.AlertType.kError)
                return
        else:
            self.pivotPower = 0

    def requestRollerOn(self):
        """Request roller spin-up. motorChecks() in periodic() drives the motor."""
        self.rollerPower = 1
        self.rollerStoppedOnce = False
        self.baselineFault = time.perf_counter()

    def requestRollerOff(self):
        """Request roller spin-down. motorChecks() in periodic() drives the motor."""
        self.rollerPower = 0
        self.baselineFault = time.perf_counter()

    def isRollerOn(self) -> bool:
        """True when roller is commanded on AND actually spinning."""
        return self.rollerPower != 0 and abs(self.rollerMotorEncoder.getVelocity()) > self.rollerStoppedThreshold

    def isRollerOff(self) -> bool:
        """True when roller velocity is below the stopped threshold."""
        return abs(self.rollerMotorEncoder.getVelocity()) <= self.rollerStoppedThreshold

    def stowIntake(self):
        if self.pivotPower >= 0 and self.pivotMotorEncoder.getPosition() >= self.pivotStowed:
            self.baselineFault = time.perf_counter()
            self.pivotPower = -1
        if self.pivotPower <= 0:
            if self.pivotMotorEncoder.getPosition() <= self.pivotStowed:
                self.pivotPower = 0
            if self.baselineFault - time.perf_counter() >= self.pivotFaultThreshold:
                wpilib.Alert("INTAKE ERR112: Intake Stow doesn't appear to be working! Stopping activation.", wpilib.Alert.AlertType.kError)
                return
        else:
            self.pivotPower = 0

    def jamDetection(self):
        if not self.jamDetected:
            self.rollerStoppedOnce = False
            if self.rollerPower == 1:
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
                self.rollerPower = -1
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
                    self.rollerPower = 1
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
        if self.pivotPower == 1:
            self.remainingRotations = self.pivotDifference - (abs(self.pivotStowed) + abs(0 - self.pivotMotorEncoder.getPosition()))
            self.pivotSlowdownPosition = self.pivotStowed + (self.pivotDifference * 0.75)
            if self.pivotMotorEncoder.getPosition() >= self.pivotSlowdownPosition:
                self.pivotPower = 0.5
        if self.pivotPower == -1:
            self.remainingRotations = self.pivotDifference - (self.pivotDeployed - self.pivotMotorEncoder.getPosition() - abs(self.pivotStowed))
            self.pivotSlowdownPosition = self.pivotDeployed - (self.pivotDifference * 0.75)
            if self.pivotMotorEncoder.getPosition() <= self.pivotSlowdownPosition:
                self.pivotPower = -0.5

    def rampIntake(self):
        if not self.pivotRampComplete:
            self.pivotDifference = abs(self.pivotStowed) + abs(self.pivotDeployed)
            self.pivotRamp = self.pivotStowed + (self.pivotDifference * 0.5)
            if self.pivotMotorEncoder.getPosition() <= self.pivotRamp:
                if self.rampPower <= 0:
                    self.baselineFault = time.perf_counter()
                    self.rampPower = 1
                    self.pivotPower = 1
                    self.pivotRamping = True
            elif self.pivotMotorEncoder.getPosition() >= self.pivotRamp:
                if self.rampPower >= 0:
                    self.baselineFault = time.perf_counter()
                    self.rampPower = -1
                    self.pivotPower = -1
                    self.pivotRamping = True

    def motorChecks(self):
        # Check if intake deployment motor is deploying without limits
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed + 15 and self.pivotPower >= 0:
            wpilib.Alert("INTAKE ERR122: Intake Motor appears to be deploying outside of limits! Motor has been disabled.", wpilib.Alert.AlertType.kError)
            self.pivotMotor.disable()

        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed - 15 and self.pivotPower <= 0:
            wpilib.Alert("INTAKE ERR122: Intake Motor appears to be stowing outside of limits! Motor has been disabled.", wpilib.Alert.AlertType.kError)
            self.pivotMotor.disable()

        # Stop intake deployment motor if it reaches limits
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed and self.pivotPower >= 0:
            self.pivotPower = 0
        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed and self.pivotPower <= 0:
            self.pivotPower = 0

        # Stop intake deployment motor if its position does not change even when it is supposed to be moving
        self.pivotMotorPositions.pop(0)
        self.pivotMotorPositions.append(self.pivotMotorEncoder.getPosition())
        if not self.pivotMotorEncoder.getPosition() <= self.pivotStowed and not self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
            if self.pivotMotorPositions.count(self.pivotMotorEncoder.getPosition()) == 5:
                if self.pivotPower == -1:
                    self.pivotStowed = self.pivotMotorEncoder.getPosition() + 1
                    self.pivotPower = 0
                elif self.pivotPower == 1:
                    self.pivotDeployed = self.pivotMotorEncoder.getPosition() - 1
                    self.pivotPower = 0

        if self.pivotPower == 0:
            self.pivotSpeed = 0
        self.rollerMotor.set(self.rollerPower * self.rollerSpeed)

        self.pivotMotor.set(self.pivotPower * self.pivotSpeed)

        # Stop pivot deployment motor if it is being ramped
        if self.pivotRamping:
            if self.rampPower == 1:
                if self.pivotMotorEncoder.getPosition() >= self.pivotRamp:
                    self.rampPower = 0
                    self.pivotPower = 0
                    self.pivotRampComplete = True
            if self.rampPower == -1:
                if self.pivotMotorEncoder.getPosition() <= self.pivotRamp:
                    self.rampPower = 0
                    self.pivotPower = 0
                    self.pivotRampComplete = True

        # Allows pivot to be ramped even from deployed/stowed position
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
            self.rampPower = 0
        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed:
            self.rampPower = 0

        if self.pivotPower != 0:
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
        wpilib.SmartDashboard.putNumber("Pivot Power", self.pivotPower)
        wpilib.SmartDashboard.putBoolean("Roller Stopped Once", self.rollerStoppedOnce)
        wpilib.SmartDashboard.putNumber("Intake Difference", self.pivotDifference)
        wpilib.SmartDashboard.putNumber("Remaining Rotations", self.remainingRotations)
        wpilib.SmartDashboard.putNumber("Intake Slowdown Position", self.pivotSlowdownPosition)
        wpilib.SmartDashboard.putNumber("Ramp Power", self.rampPower)
        wpilib.SmartDashboard.putNumber("Intake Ramp Position", self.pivotRamp)
        wpilib.SmartDashboard.putBoolean("Intake Ramp Complete", self.pivotRampComplete)
        wpilib.SmartDashboard.putNumberArray("Intake Positions", self.pivotMotorPositions)
        wpilib.SmartDashboard.putNumber("Intake Stowed", self.pivotStowed)
        wpilib.SmartDashboard.putNumber("Roller Power", self.rollerPower)
        wpilib.SmartDashboard.putBoolean("Roller Jam", self.jamDetected)
        wpilib.SmartDashboard.putNumber("Actual Roller Velocity", self.rollerMotorEncoder.getVelocity())
        wpilib.SmartDashboard.putNumber("Baseline Detected Jam", self.baselineDetectedJam)
        wpilib.SmartDashboard.putNumber("Pivot Motor Output", self.pivotPower * self.pivotSpeed)
        wpilib.SmartDashboard.putNumber("Baseline Jam", self.baselineJam)

        self.motorChecks()
        # self.automaticRollerActivation()
        self.pivotSlowdown()
        self.jamDetection()
