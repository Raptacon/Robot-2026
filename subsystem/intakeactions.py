import wpilib
import commands2
import rev
import time
import os
import ntcore
import array as arr

from constants import CaptainPlanetConsts as intakeConsts

intakeVelocity = 0.3 #Speed (in rpm) in which the intake motor will move upon deployment/stowing
intakeMotorThreshold = 1 #Used to determine whether or not intake is deployed
intakeFaultThreshold = 10 #Amount of time spent trying to deploy/stow intake before fault condition is triggered
rollerVelocity = 0.3 #Speed in which the roller motor will move upon deployment
rollerFaultThreshold = 10 #Amount of time spent trying to operate rollers before fault condition is triggered
jamFaultThreshold = 10 #Amount of attempts done trying to reverse rollers in the event of a jam before a fault condition is triggered

baselineFault = 0 #Leave at 0, provides baseline to compare to when determining faults
baselineJam = 0 #Leave at 0, provides baseline to compare to when determining faults
jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered

class IntakeSubsystem(commands2.SubsystemBase):
    def __init__(self, hasSecondMotor = True):
        #Initialize Intake
        self.intakeMotor = rev.SparkFlex(intakeConsts.kIntakeMotorCanId, rev.SparkLowLevel.MotorType.kBrushless)
        self.intakeMotorEncoder = self.intakeMotor.getEncoder()
        #self.intakeMotorPosition = self.intakeMotorEncoder.getPosition()

        self.hasSecondMotor = hasSecondMotor
        #Initialize Roller
        if self.hasSecondMotor:
            self.rollerMotor = rev.SparkMax(intakeConsts.kRollerMotorCanId, rev.SparkLowLevel.MotorType.kBrushless)
            self.rollerMotorEncoder = self.rollerMotor.getEncoder()
            self.rollerMotorVelocity = self.rollerMotorEncoder.getVelocity()

        #Initialize Break Beams
        self.breakBeam = wpilib.DigitalInput(intakeConsts.kBreakBeam)
        #self.frontBreakbeam = wpilib.DigitalInput(intakeConsts.kFrontBreakBeam)
        #self.backBreakbeam = wpilib.DigitalInput(intakeConsts.kBackBreakBeam)
        #self.frontBeamBroken = not self.frontBreakbeam.get()
        #self.backBeamBroken = not self.backBreakbeam.get()

        self.HallEffectSensor = wpilib.DigitalInput(intakeConsts.kHallEffectSensor)

        #Set Variables
        self.intakeDeployed = 200 #Minimum amount of rotations before assuming intake is deployed
        self.intakeStowed = 0 #Maximum amount of rotations before assuming intake is stowed 
        self.intakeFaultThreshold = 2 #Amount of time spent trying to deploy/stow intake before fault condition is triggered
        self.intakeMagnetFaultThreshold = 2 #Amount of time before magnets need to have stopped tripping hall effects sensor or fault condition is triggered
        self.rollerFaultThreshold = 2 #Amount of time spent trying to operate rollers before fault condition is triggered
        self.jamFaultThreshold = 0 #Amount of attempts done trying to reverse rollers in the event of a jam before a fault condition is triggered
        self.jamTime = 0.5 #Amount of time to wait before assuming a ball inside the intake has gotten stuck
        self.jamThreshold = 75 #Minimum voltage before assuming a ball inside the intake has gotten stuck
        self.jamReversalTime = 0.5 #Amount of time to have motors reverse when a ball inside the intake has gotten stuck


        self.intakeCondition = 0 #Leave at 0, provides reference to code on current intake status
        self.intakeRamped = 0 #Leave at 0, provides reference to code on ramping intake status
        self.intakeRampedCondition = 0 #Leave at 0, provides reference to code on whether ramping intake is finished
        self.intakeVelocity = 0 #Leave at 0, any updating is to be done thru Network Table, Speed (in rpm) in which the intake motor will move upon deployment/stowing
        self.rollerVelocity = 0 #Leave at 0, any updating is to be done thru Network Table, Speed in which the roller motor will move upon deployment
        self.baselineFault = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.baselineJam = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered
        self.intakeDifference = 0 #Leave at 0, rotations required to get from intake stowed position to intake deployed position is automatically calculated
        self.remainingRotations = 0 #Leave at 0, rotations remaining to finish deploying/stowing intake is automatically calculated
        self.intakeSlowdownPosition = 0 #Leave at 0, stores amount of intake motor rotations required to slow it down
        self.intakeRamp = 0 #Leave at 0, motor position for ramp is automatically calculated
        self.intakeRampStatus = 0 #Leave at 0, provides reference to code on whether intake is moving to ramp
        self.hardStopIndex = 0 #Leave at 0, provides index to code for hardstop checks
        self.jamOccurence = 0 #Leave at 0, provides baseline to compare to when determining jams
        self.baselineDetectedJam = 0 #Leave at 0, provides baseline to compare to when jam detection is activated
        self.rollerCondition = 0 #Leave at 0, provides reference to code on current roller status
        self.rollerSensor = 0 #Leave at 0, ensures that the rollers are stopped only once, preventing obstruction of manual controls
        
        
        self.jamDetected = False #Leave at False
        self.intakeMotorPositions = arr.array('f', [0,0,0,0,0]) #Leave with all zeros, for checking if intake motor stopped during deployment/stowing


    def deployIntake(self):
        #Check Sensor for deployment, if not, deploy it.
        if self.intakeCondition <= 0 and self.intakeMotorEncoder.getPosition() <= self.intakeDeployed:
                self.baselineFault = time.perf_counter()
                self.intakeCondition = 1
        if self.intakeCondition >= 0:
            if self.HallEffectSensor.get() == False:
                self.intakeDeployed = self.intakeMotorEncoder.getPosition()
                self.intakeCondition = 0          
            if self.intakeMotorEncoder.getPosition() >= self.intakeDeployed:
                self.intakeCondition = 0
            if self.baselineFault - time.perf_counter() >= self.intakeFaultThreshold:
                print("INTAKE ERR101: Deployment of Intake doesn't appear to be working! Stopping code.")
                os._exit(101)
        else:
            self.intakeCondition = 0

    def activateRoller(self):
        if self.hasSecondMotor:
            #self.baselineFault = time.perf_counter()
            
            #Apply voltage to roller until it starts moving; Terminate program with ERR103 if fault condition is detected
            #while self.rollerMotorEncoder.getVelocity() == 0:
            if self.rollerCondition != 1:
                self.rollerCondition = 1
                #if baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                    #os._exit(103)

    def deactivateRoller(self):
        #if self.hasSecondMotor:
            #self.baselineFault = time.perf_counter()
        
            #Try to terminate voltage until motor stops moving; Terminate program with ERR103 if fault condition is detected
            #while self.rollerMotorEncoder.getVelocity() != 0:
            if self.rollerCondition != 0:
                self.rollerCondition = 0
                #if baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                    #os._exit(103)

    def stowIntake(self):
        if self.intakeCondition >= 0 and self.intakeMotorEncoder.getPosition() >= self.intakeStowed:
                self.baselineFault = time.perf_counter()
                self.intakeCondition = -1
        if self.intakeCondition <= 0:
            if self.intakeMotorEncoder.getPosition() <= self.intakeStowed:
                self.intakeCondition = 0
            if self.baselineFault - time.perf_counter() >= self.intakeFaultThreshold:
                print("INTAKE ERR102: Intake stow doesn't appear to be working! Stopping code.")
                os._exit(102)
            if self.intakeMagnetFaultThreshold + 1 >= time.perf_counter() - self.baselineFault >= self.intakeMagnetFaultThreshold:
                if self.HallEffectSensor.get() == False:
                    print("INTAKE ERR112: Intake motor is engaged but the Intake doesn't appear to be moving! Stopping code.")
                    os._exit(112)
        else:
            self.intakeCondition = 0

    def jamDetection(self):
        if self.hasSecondMotor:
            if not self.jamDetected:
                if self.rollerMotor.getOutputCurrent() >= self.jamThreshold:
                    if self.jamOccurence == 0:
                        self.baselineJam = time.perf_counter()
                        self.jamOccurence = 1
                    else:
                            self.baselineDetectedJam = time.perf_counter()
                            self.jamDetected = True
            else:
                if time.perf_counter() - self.baselineDetectedJam <= self.jamReversalTime:
                    self.rollerCondition = -1
                else:
                    self.rollerCondition = 1
                    self.jamDetected = False

    def updateIntake(self, newIntakeVelocity):
        self.intakeVelocity = newIntakeVelocity

    def updateRoller(self, newRollerVelocity):
        self.rollerVelocity = newRollerVelocity

    def automaticRollerActivation(self):
        if not self.breakBeam.get():
            self.rollerSensor = 1
            self.activateRoller()
        else:
            if self.rollerSensor == 1:
                self.deactivateRoller()
                self.rollerSensor = 0

    def intakeSlowdown(self):
        self.intakeDifference = abs(self.intakeStowed) + abs(self.intakeDeployed)
        #Slows down deployment of motor when slowdown position is reached
        if self.intakeCondition == 1: 
            self.remainingRotations = self.intakeDifference - (abs(self.intakeStowed) + abs(0 - self.intakeMotorEncoder.getPosition()))
            self.intakeSlowdownPosition = self.intakeStowed + (self.intakeDifference * 0.75)
            if self.intakeMotorEncoder.getPosition() >= self.intakeSlowdownPosition:
                self.intakeCondition = 0.5
        #Slows down stowing of motor when slowdown position is reached
        if self.intakeCondition == -1:
            self.remainingRotations = self.intakeDifference - (self.intakeDeployed - self.intakeMotorEncoder.getPosition() - abs(self.intakeStowed))
            self.intakeSlowdownPosition = self.intakeDeployed - (self.intakeDifference * 0.75)
            if self.intakeMotorEncoder.getPosition() <= self.intakeSlowdownPosition:
                self.intakeCondition = -0.5

    def rampIntake(self):
        if not self.intakeRampedCondition:
            self.intakeDifference = abs(self.intakeStowed) + abs(self.intakeDeployed)
            self.intakeRamp = self.intakeStowed + (self.intakeDifference * 0.5)
            if self.intakeMotorEncoder.getPosition() <= self.intakeRamp:
                if self.intakeRamped <= 0:
                    self.baselineFault = time.perf_counter()
                    self.intakeRamped = 1
                    self.intakeCondition = 1
                    self.intakeRampStatus = 1
            elif self.intakeMotorEncoder.getPosition() >= self.intakeRamp:
                if self.intakeRamped >= 0:
                        self.baselineFault = time.perf_counter()
                        self.intakeRamped = -1
                        self.intakeCondition = -1
                        self.intakeRampStatus = 1

    def motorChecks(self):
        #Check if intake deployment motor is deploying without limits
        if self.intakeMotorEncoder.getPosition() >= self.intakeDeployed + 15 and self.intakeCondition >= 0:
            print("INTAKE ERR121: Intake Motor appears to be deploying outside of limits! Motor has been disabled.")
            self.intakeMotor.disable()
        if self.intakeMotorEncoder.getPosition() <= self.intakeStowed - 15 and self.intakeCondition <= 0:
            print("INTAKE ERR122: Intake Motor appears to be stowing outside of limits! Motor has been disabled.")
            self.intakeMotor.disable()
        
        #Stop intake deployment motor if it reaches limits
        if self.intakeMotorEncoder.getPosition() >= self.intakeDeployed and self.intakeCondition >= 0:
            self.intakeCondition = 0
        if self.intakeMotorEncoder.getPosition() <= self.intakeStowed and self.intakeCondition <= 0:
            self.intakeCondition = 0

        
        #Stop intake deployment motor if it's position does not change even when it is supposed to be moving
        self.intakeMotorPositions.pop(0)
        self.intakeMotorPositions.append(self.intakeMotorEncoder.getPosition())
        if not self.intakeMotorEncoder.getPosition() <= self.intakeStowed and not self.intakeMotorEncoder.getPosition() >= self.intakeDeployed:
            if self.intakeMotorPositions.count(self.intakeMotorEncoder.getPosition()) == 5:
                    if self.intakeCondition == -1:
                        self.intakeStowed = self.intakeMotorEncoder.getPosition() + 1
                        self.intakeCondition = 0
                    elif self.intakeCondition == 1:
                        self.intakeDeployed = self.intakeMotorEncoder.getPosition() - 1
                        self.intakeCondition = 0

        if self.intakeCondition == 0:
            self.intakeVelocity = 0
        self.intakeMotor.set(self.intakeCondition * self.intakeVelocity)
        self.rollerMotor.set(self.rollerCondition * self.rollerVelocity)

        #Stop intake deployment motor if it is being ramped
        if self.intakeRampStatus == 1:
            if self.intakeRamped == 1:
                    if self.intakeMotorEncoder.getPosition() >= self.intakeRamp:
                        self.intakeRamped = 0
                        self.intakeCondition = 0
                        self.intakeRampedCondition = True   
            if self.intakeRamped == -1:
                    if self.intakeMotorEncoder.getPosition() <= self.intakeRamp:
                        self.intakeRamped = 0
                        self.intakeCondition = 0
                        self.intakeRampedCondition = True
        
        #Allows intake to be ramped even from deployed/stowed position
        if self.intakeMotorEncoder.getPosition() >= self.intakeDeployed:
            self.intakeRamped = 0
        if self.intakeMotorEncoder.getPosition() <= self.intakeStowed:
            self.intakeRamped = 0

        if self.intakeCondition != 0:
            self.intakeRampedCondition = False


    def periodic(self):
        wpilib.SmartDashboard.putNumber("Intake Position", self.intakeMotorEncoder.getPosition())
        wpilib.SmartDashboard.putNumber("Roller Position", self.rollerMotorEncoder.getPosition())
        wpilib.SmartDashboard.putNumber("Intake Deployed", self.intakeDeployed)
        wpilib.SmartDashboard.putBoolean("Hall Effects Sensor", self.HallEffectSensor.get())
        wpilib.SmartDashboard.putNumber("Time", time.perf_counter())
        wpilib.SmartDashboard.putNumber("Baseline Fault", self.baselineFault)
        wpilib.SmartDashboard.putNumber("Intake Condition", self.intakeCondition)
        wpilib.SmartDashboard.putBoolean("Break Beam Sensor", self.breakBeam.get())
        wpilib.SmartDashboard.putNumber("Roller Sensor", self.rollerSensor)
        wpilib.SmartDashboard.putNumber("Intake Difference", self.intakeDifference)
        wpilib.SmartDashboard.putNumber("Remaining Rotations", self.remainingRotations)
        wpilib.SmartDashboard.putNumber("Intake Slowdown Position", self.intakeSlowdownPosition)
        wpilib.SmartDashboard.putNumber("Intake Ramped", self.intakeRamped)
        wpilib.SmartDashboard.putNumber("Intake Ramp Position", self.intakeRamp)
        wpilib.SmartDashboard.putBoolean("Intake Ramp Condition", self.intakeRampedCondition)
        wpilib.SmartDashboard.putNumberArray("Intake Positions", self.intakeMotorPositions)
        wpilib.SmartDashboard.putNumber("Intake Stowed", self.intakeStowed)
        
        self.motorChecks()
        self.automaticRollerActivation()
        self.intakeSlowdown()
        self.jamDetection()