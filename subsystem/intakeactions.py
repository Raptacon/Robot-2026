import wpilib
import commands2
import rev
import time
import os
import ntcore
from constants import CaptainPlanetConsts as intakeConsts

class IntakeSubsystem(commands2.SubsystemBase):
    def __init__(self, hasSecondMotor = True):
        #Initialize Intake
        self.intakeMotor = rev.SparkFlex(11, rev.SparkLowLevel.MotorType.kBrushless)
        self.intakeMotorEncoder = self.intakeMotor.getEncoder()
        #self.intakeMotorPosition = self.intakeMotorEncoder.getPosition()

        self.hasSecondMotor = hasSecondMotor
        #Initialize Roller
        if self.hasSecondMotor:
            self.rollerMotor = rev.SparkMax(56, rev.SparkLowLevel.MotorType.kBrushless)
            self.rollerMotorEncoder = self.rollerMotor.getEncoder()
            self.rollerMotorEncoder.setPosition(0)
            #self.rollerMotorVelocity = self.rollerMotorEncoder.getVelocity()

        #Initialize Break Beams
        self.frontBreakbeam = wpilib.DigitalInput(intakeConsts.kFrontBreakBeam)
        self.backBreakbeam = wpilib.DigitalInput(intakeConsts.kBackBreakBeam)
        self.frontBeamBroken = not self.frontBreakbeam.get()
        self.backBeamBroken = not self.backBreakbeam.get()

        self.HallEffectSensor = wpilib.DigitalInput(6)

        #Set Variables
        self.intakeDeployed = 100 #Minimum amount of rotations before assuming intake is deployed
        self.intakeStowed = 0 #Maximum amount of rotations before assuming intake is deployed
        self.intakeFaultThreshold = 20 #Amount of time spent trying to deploy/stow intake before fault condition is triggered
        self.rollerFaultThreshold = 20 #Amount of time spent trying to operate rollers before fault condition is triggered
        self.jamTime = 3 #Amount of time to wait before assuming a ball inside the intake has gotten stuck
        self.jamFaultThreshold = 0 #Amount of attempts done trying to reverse rollers in the event of a jam before a fault condition is triggered
        self.rollerDuration = 50 #Amount of rotations before stopping Roller Motor

        self.intakeVelocity = 0 #Leave at zero - any updating is to be done thru Network Table, Speed (in rpm) in which the intake motor will move upon deployment/stowing
        self.rollerVelocity = 0 #Leave at zero - any updating is to be done thru Network Table, Speed in which the roller motor will move upon deployment
        self.baselineFault = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.rollerOccurence = 0 #Leave at 0, provides reference for timed roller activation
        self.intakeCondition = 0 #Leave at 0, provides reference for intake fault detection
        self.rollerStop = 0 #Leave at 0, stores amount of rotations to stop at during timed roller activation
        self.baselineJam = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered

    def deployIntake(self):
        #Check Sensor for deployment, if not, deploy it.
        if self.intakeMotorEncoder.getPosition() <= self.intakeDeployed:
            if self.intakeCondition <= 0:
                self.baselineFault = time.perf_counter() #Set Baseline for Fault Detection
                self.intakeCondition = 1
            self.intakeMotor.set(self.intakeVelocity)
            if self.baselineFault - time.perf_counter() >= self.intakeFaultThreshold:
                os._exit(101)
        else:
            self.intakeVelocity = 0
            self.intakeCondition = 0
            self.intakeMotor.set(self.intakeVelocity)


    def activateRoller(self):
        if self.hasSecondMotor:
            self.baselineFault = time.perf_counter() #Set Baseline for Fault Detection
            
            self.rollerMotor.set(self.rollerVelocity)
            if self.baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                os._exit(103)

    def deactivateRoller(self):
        if self.hasSecondMotor:
            self.baselineFault = time.perf_counter() #Set Baseline for Fault Detection
        
            #Try to terminate voltage until motor stops moving; Terminate program with ERR103 if fault condition is detected
            self.rollerMotor.set(0)
            if self.baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                os._exit(103)

    def timedRollerActivation(self):
        if self.hasSecondMotor:
            if self.rollerOccurence == 0:
                self.rollerStop = float(self.rollerMotorEncoder.getPosition()) + float(self.rollerDuration)
                self.rollerOccurence = 1
            if self.rollerMotorEncoder.getPosition() <= self.rollerStop:
                self.rollerMotor.set(self.rollerVelocity)
            else:
                self.rollerVelocity = 0
                self.rollerOccurence = 0
                self.rollerMotor.set(self.rollerVelocity)
                commands2.CommandScheduler.getInstance().cancelAll()

    def stowIntake(self):
        if self.intakeMotorEncoder.getPosition() >= self.intakeStowed:
            if self.intakeCondition >= 0:
                self.baselineFault = time.perf_counter() #Set Baseline for Fault Detection
                self.intakeCondition = -1      
            self.intakeMotor.set(-self.intakeVelocity)
            if self.baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                os._exit(102)
        else:
            self.intakeVelocity = 0
            self.intakeCondition = 0
            self.intakeMotor.set(0)

    def jamDetection(self):
        if self.hasSecondMotor:
            if self.frontBeamBroken:
                baselineJam = time.perf_counter() #Set Baseline for Jam Detection
                while not self.backBeamBroken:
                    #If Ball appears to have jammed, reverse rollers
                    if self.baselineFault - time.perf_counter >= self.rollerFaultThreshold:
                        self.baselineFault = time.perf_counter() #Set Baseline for Fault Detection
            
                        #Reverse voltage to motor until front sensors go off; Terminate program with ERR104 if fault condition is detected
                        while not self.frontBeamBroken:
                            if self.rollerMotorVelocity >= 0:
                                jamReversalCount += 1
                                self.rollerMotor.set(-self.rollerVelocity)
                            elif jamReversalCount >= self.jamFaultThreshold:
                                os._exit(104)  
    
    def updateIntake(self, newIntakeVelocity):
        self.intakeVelocity = newIntakeVelocity

    def updateRoller(self, newRollerVelocity):
        self.rollerVelocity = newRollerVelocity

    def periodic(self):
        wpilib.SmartDashboard.putNumber("Intake Position", self.intakeMotorEncoder.getPosition())
        wpilib.SmartDashboard.putNumber("Roller Position", self.rollerMotorEncoder.getPosition())
