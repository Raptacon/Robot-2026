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
        self.pivotVelocity = 0.3 #Velocity intake moves upon deploying/stow
        self.rollerVelocity = 0.3 #Velocity rollers move upon activation

        self.pivotCondition = 0 #Leave at 0, provides reference to code on current intake status
        self.pivotRamped = 0 #Leave at 0, provides reference to code on ramping intake status
        self.pivotRampedCondition = 0 #Leave at 0, provides reference to code on whether ramping intake is finished
        self.baselineFault = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.baselineJam = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered
        self.pivotDifference = 0 #Leave at 0, rotations required to get from intake stowed position to intake deployed position is automatically calculated
        self.remainingRotations = 0 #Leave at 0, rotations remaining to finish deploying/stowing intake is automatically calculated
        self.pivotSlowdownPosition = 0 #Leave at 0, stores amount of intake motor rotations required to slow it down
        self.pivotRamp = 0 #Leave at 0, motor position for ramp is automatically calculated
        self.pivotRampStatus = 0 #Leave at 0, provides reference to code on whether intake is moving to ramp
        self.hardStopIndex = 0 #Leave at 0, provides index to code for hardstop checks
        self.jamOccurence = 0 #Leave at 0, provides baseline to compare to when determining jams
        self.baselineDetectedJam = 0 #Leave at 0, provides baseline to compare to when jam detection is activated
        self.rollerCondition = 0 #Leave at 0, provides reference to code on current roller status
        self.rollerSensor = 0 #Leave at 0, ensures that the rollers are stopped only once, preventing obstruction of manual controls
        
        self.jamDetected = False #Leave at False
        self.pivotMotorPositions = array.array('f', [0,0,0,0,0]) #Leave with all zeros, for checking if intake motor stopped during deployment/stowing

    def deployIntake(self):
        #Check Sensor for deployment, if not, deploy it.
        if self.pivotCondition <= 0 and self.pivotMotorEncoder.getPosition() <= self.pivotDeployed:
            self.baselineFault = time.perf_counter()
            self.pivotCondition = 1
        if self.pivotCondition >= 0:
            # if self.HallEffectSensor.get() == False:
            #     self.pivotDeployed = self.pivotMotorEncoder.getPosition()
            #     self.pivotCondition = 0
            if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
                self.pivotCondition = 0
            if self.baselineFault - time.perf_counter() >= self.pivotFaultThreshold:
                wpilib.Alert("INTAKE ERR101: Deployment of intake dosen't appear to be working! Stopped activation.", wpilib.Alert.AlertType.kError)
                return
        else:
            self.pivotCondition = 0

    def activateRoller(self):
        self.baselineFault = time.perf_counter()
        
        # Apply voltage to roller until it starts moving; Terminate program with ERR103 if fault condition is detected
        while self.rollerMotorEncoder.getVelocity() == 0:
            if self.rollerCondition != 1:
                self.rollerCondition = 1
                self.rollerSensor = 0
            if self.baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                wpilib.Alert("INTAKE ERR103: Activation of rollers don't appear to be working! Stopped activation.", wpilib.Alert.AlertType.kError)
                return

    def deactivateRoller(self):
        self.baselineFault = time.perf_counter()
    
        # Try to terminate voltage until motor stops moving; Terminate program with ERR103 if fault condition is detected
        while self.rollerMotorEncoder.getVelocity() != 0:
            if self.rollerCondition != 0:
                self.rollerCondition = 0
                if self.baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                    wpilib.Alert("INTAKE ERR103: Activation of rollers don't appear to be working! Stopped activation.", wpilib.Alert.AlertType.kError)
                    return

    def stowIntake(self):
        if self.pivotCondition >= 0 and self.pivotMotorEncoder.getPosition() >= self.pivotStowed:
            self.baselineFault = time.perf_counter()
            self.pivotCondition = -1
        if self.pivotCondition <= 0:
            if self.pivotMotorEncoder.getPosition() <= self.pivotStowed:
                self.pivotCondition = 0
            if self.baselineFault - time.perf_counter() >= self.pivotFaultThreshold:
                wpilib.Alert("INTAKE ERR112: Intake Stow doesn't appear to be working! Stopping activation.", wpilib.Alert.AlertType.kError)
                return
            # if self.pivotMagnetFaultThreshold + 1 >= time.perf_counter() - self.baselineFault >= self.pivotMagnetFaultThreshold:
            #     if self.HallEffectSensor.get() == False:
            #           wpilib.Alert("INTAKE ERR112: Intake motor is engaged but the Intake doesn't appear to be moving! Stopping code.", wpilib.Alert.AlertType.kError)
            #           return
        else:
            self.pivotCondition = 0

    def jamDetection(self):
        if not self.jamDetected:
            self.rollerSensor = 0
            if self.rollerCondition == 1:
                if self.rollerMotorEncoder.getVelocity() <= self.jamThreshold:
                    if self.jamOccurence == 0:
                        self.baselineJam = time.perf_counter()
                        self.jamOccurence = 1
                    else:
                        if time.perf_counter() - self.baselineJam >= self.jamTime:
                            self.baselineDetectedJam = time.perf_counter()
                            self.jamDetected = True
                else:
                    self.jamOccurence = 0
        else:
            if time.perf_counter() - self.baselineDetectedJam <= self.jamReversalTime and self.jamOccurence == 1:
                self.rollerCondition = -1
                if abs(self.rollerMotorEncoder.getVelocity()) >= self.unjam:
                    self.jamOccurence = 0
            else:
                if self.rollerMotorEncoder.getVelocity() <= self.unjam:
                    wpilib.Alert("Jam reversal unsuccessful! Stopping motor.", wpilib.Alert.AlertType.kError)
                    self.rollerMotor.disable()
                if self.rollerSensor == 0:
                    self.deactivateRoller()
                    self.rollerSensor = 1
                else:
                    self.rollerCondition = 1
                    self.jamOccurence = 0
                    self.jamDetected = False

    # def automaticRollerActivation(self):
        # if not self.breakBeam.get():
        #     self.rollerSensor = 1
        #     self.activateRoller()
        # else:
        #     if self.rollerSensor == 1:
        #         self.deactivateRoller()
        #         self.rollerSensor = 0

    def pivotSlowdown(self):
        self.pivotDifference = abs(self.pivotStowed) + abs(self.pivotDeployed)
        if self.pivotCondition == 1:
            self.remainingRotations = self.pivotDifference - (abs(self.pivotStowed) + abs(0 - self.pivotMotorEncoder.getPosition()))
            self.pivotSlowdownPosition = self.pivotStowed + (self.pivotDifference * 0.75)
            if self.pivotMotorEncoder.getPosition() >= self.pivotSlowdownPosition:
                self.pivotCondition = 0.5
        if self.pivotCondition == -1:
            self.remainingRotations = self.pivotDifference - (self.pivotDeployed - self.pivotMotorEncoder.getPosition() - abs(self.pivotStowed))
            self.pivotSlowdownPosition = self.pivotDeployed - (self.pivotDifference * 0.75)
            if self.pivotMotorEncoder.getPosition() <= self.pivotSlowdownPosition:
                self.pivotCondition = -0.5

    def rampIntake(self):
        if not self.pivotRampedCondition:
            self.pivotDifference = abs(self.pivotStowed) + abs(self.pivotDeployed)
            self.pivotRamp = self.pivotStowed + (self.pivotDifference * 0.5)
            if self.pivotMotorEncoder.getPosition() <= self.pivotRamp:
                if self.pivotRamped <= 0:
                    self.baselineFault = time.perf_counter()
                    self.pivotRamped = 1
                    self.pivotCondition = 1
                    self.pivotRampStatus = 1
            elif self.pivotMotorEncoder.getPosition() >= self.pivotRamp:
                if self.pivotRamped >= 0:
                    self.baselineFault = time.perf_counter()
                    self.pivotRamped = -1
                    self.pivotCondition = -1
                    self.pivotRampStatus = 1

    def motorChecks(self):
        # Check if intake deployment motor is deploying without limits
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed + 15 and self.pivotCondition >= 0:
            wpilib.Alert("INTAKE ERR122: Intake Motor appears to be deploying outside of limits! Motor has been disabled.", wpilib.Alert.AlertType.kError)
            self.pivotMotor.disable()

        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed - 15 and self.pivotCondition <= 0:
            wpilib.Alert("INTAKE ERR122: Intake Motor appears to be stowing outside of limits! Motor has been disabled.", wpilib.Alert.AlertType.kError)
            self.pivotMotor.disable()

        
        #Stop intake deployment motor if it reaches limits
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed and self.pivotCondition >= 0:
            self.pivotCondition = 0
        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed and self.pivotCondition <= 0:
            self.pivotCondition = 0

        
        #Stop intake deployment motor if it's position does not change even when it is supposed to be moving
        self.pivotMotorPositions.pop(0)
        self.pivotMotorPositions.append(self.pivotMotorEncoder.getPosition())
        if not self.pivotMotorEncoder.getPosition() <= self.pivotStowed and not self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
            if self.pivotMotorPositions.count(self.pivotMotorEncoder.getPosition()) == 5:
                if self.pivotCondition == -1:
                    self.pivotStowed = self.pivotMotorEncoder.getPosition() + 1
                    self.pivotCondition = 0
                elif self.pivotCondition == 1:
                    self.pivotDeployed = self.pivotMotorEncoder.getPosition() - 1
                    self.pivotCondition = 0

        if self.pivotCondition == 0:
            self.pivotVelocity = 0
        self.rollerMotor.set(self.rollerCondition * self.rollerVelocity)
        
        self.pivotMotor.set(self.pivotCondition * self.pivotVelocity)
        # self.pivotMotorPID.setReference(
        #     self.pivotCondition * self.pivotVelocity, rev.SparkLowLevel.ControlType.kVelocity, rev.ClosedLoopSlot.kSlot0
        # )

        # Stop pivot deployment motor if it is being ramped
        if self.pivotRampStatus == 1:
            if self.pivotRamped == 1:
                if self.pivotMotorEncoder.getPosition() >= self.pivotRamp:
                    self.pivotRamped = 0
                    self.pivotCondition = 0
                    self.pivotRampedCondition = True
            if self.pivotRamped == -1:
                if self.pivotMotorEncoder.getPosition() <= self.pivotRamp:
                    self.pivotRamped = 0
                    self.pivotCondition = 0
                    self.pivotRampedCondition = True
        
        #Allows pivot to be ramped even from deployed/stowed position
        if self.pivotMotorEncoder.getPosition() >= self.pivotDeployed:
            self.pivotRamped = 0
        if self.pivotMotorEncoder.getPosition() <= self.pivotStowed:
            self.pivotRamped = 0

        if self.pivotCondition != 0:
            self.pivotRampedCondition = False

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
        wpilib.SmartDashboard.putNumber("Intake Condition", self.pivotCondition)
        # wpilib.SmartDashboard.putBoolean("Break Beam Sensor", self.breakBeam.get())
        wpilib.SmartDashboard.putNumber("Roller Sensor", self.rollerSensor)
        wpilib.SmartDashboard.putNumber("Intake Difference", self.pivotDifference)
        wpilib.SmartDashboard.putNumber("Remaining Rotations", self.remainingRotations)
        wpilib.SmartDashboard.putNumber("Intake Slowdown Position", self.pivotSlowdownPosition)
        wpilib.SmartDashboard.putNumber("Intake Ramped", self.pivotRamped)
        wpilib.SmartDashboard.putNumber("Intake Ramp Position", self.pivotRamp)
        wpilib.SmartDashboard.putBoolean("Intake Ramp Condition", self.pivotRampedCondition)
        wpilib.SmartDashboard.putNumberArray("Intake Positions", self.pivotMotorPositions)
        wpilib.SmartDashboard.putNumber("Intake Stowed", self.pivotStowed)
        wpilib.SmartDashboard.putNumber("Roller Condition", self.rollerCondition)
        wpilib.SmartDashboard.putBoolean("Roller Jam", self.jamDetected)
        wpilib.SmartDashboard.putNumber("Actual Roller Velocity", self.rollerMotorEncoder.getVelocity())
        wpilib.SmartDashboard.putNumber("Baseline Detected Jam", self.baselineDetectedJam)
        wpilib.SmartDashboard.putNumber("Intake Condition * Velocity", self.pivotCondition * self.pivotVelocity)
        wpilib.SmartDashboard.putNumber("Baseline Jam", self.baselineJam)

        self.motorChecks()
        # self.automaticRollerActivation()
        self.pivotSlowdown()
        self.jamDetection()
