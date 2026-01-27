import wpilib
import commands2
import rev
import time
import os

from constants import CaptainPlanetConsts as intakeConsts

intakeVelocity = 0.3 #Speed (in rpm) in which the intake motor will move upon deployment/stowing
intakeMotorThreshold = 1 #Used to determine whether or not intake is deployed
intakeFaultThreshold = 2 #Amount of time spent trying to deploy/stow intake before fault condition is triggered
rollerVelocity = 0.3 #Speed in which the roller motor will move upon deployment
rollerFaultThreshold = 2 #Amount of time spent trying to operate rollers before fault condition is triggered
jamTime = 3 #Amount of time to wait before assuming a ball inside the intake has gotten stuck
jamFaultThreshold = 0 #Amount of attempts done trying to reverse rollers in the event of a jam before a fault condition is triggered

baselineFault = 0 #Leave at 0, provides baseline to compare to when determining faults
baselineJam = 0 #Leave at 0, provides baseline to compare to when determining faults
jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered

class IntakeSubsystem(commands2.SubsystemBase):
    def __init__(self):
        #Initialize Intake
        self.intakeMotor = rev.SparkFlex(11, rev.SparkLowLevel.MotorType.kBrushless)
        self.intakeMotorEncoder = self.intakeMotor.getEncoder()
        self.intakeMotorPosition = self.intakeMotorEncoder.getPosition()

        #Initialize Roller
        self.rollerMotor = rev.SparkFlex(2, rev.SparkLowLevel.MotorType.kBrushless)
        self.rollerMotorEncoder = self.rollerMotor.getEncoder()
        self.rollerMotorVelocity = self.rollerMotorEncoder.getVelocity()

        #Initialize Break Beams
        self.frontBreakbeam = wpilib.DigitalInput(intakeConsts.kFrontBreakBeam)
        self.backBreakbeam = wpilib.DigitalInput(intakeConsts.kBackBreakBeam)
        self.frontBeamBroken = not self.frontBreakbeam.get()
        self.backBeamBroken = not self.backBreakbeam.get()

    def deployIntake(self):
        #Check Sensor for deployment, if not, deploy it.
        if self.intakeMotorPosition == 0:
            baselineFault = time.perf_counter() #Set Baseline for Fault Detection

            #Runs until Sensor returns deployment complete; Terminate program with ERR101 if fault condition is detected
            while True:
                self.intakeMotor.set(intakeVelocity)
                if self.intakeMotorPosition >= intakeMotorThreshold:
                    self.intakeMotor.set(0)
                    break
                if baselineFault - time.perf_counter() >= intakeFaultThreshold:
                    os._exit(101)

    def activateRoller(self):
        baselineFault = time.perf_counter() #Set Baseline for Fault Detection
        
        #Apply voltage to roller until it starts moving; Terminate program with ERR103 if fault condition is detected
        while self.rollerMotorVelocity == 0:
            self.rollerMotor.set(rollerVelocity)
            if baselineFault - time.perf_counter() >= rollerFaultThreshold:
                os._exit(103)
            pass #Gets rid of indentation error

    def deactivateRoller(self):
        baselineFault = time.perf_counter() #Set Baseline for Fault Detection
    
        #Try to terminate voltage until motor stops moving; Terminate program with ERR103 if fault condition is detected
        while self.rollerMotorVelocity != 0:
            self.rollerMotor.set(0)
            if baselineFault - time.perf_counter() >= rollerFaultThreshold:
                os._exit(103)
            pass #Gets rid of indentation error

    def stowIntake(self):
        if self.intakeMotorPosition != 0:
            baselineFault = time.perf_counter() #Set Baseline for Fault Detection

            #Runs until Sensor returns stow complete; Terminate program with ERR102 if fault condition is detected
            while True:
                self.intakeMotor.set(-intakeVelocity)
                if self.intakeMotorPosition == 0:
                    self.intakeMotor.set(0)
                    break
                if baselineFault - time.perf_counter() >= rollerFaultThreshold:
                    os._exit(102)


    def jamDetection(self):
        if self.frontBeamBroken:
            baselineJam = time.perf_counter() #Set Baseline for Jam Detection
            while not self.backBeamBroken:
                #If Ball appears to have jammed, reverse rollers
                if baselineFault - time.perf_counter >= rollerFaultThreshold:
                    baselineFault = time.perf_counter() #Set Baseline for Fault Detection
        
                    #Reverse voltage to motor until front sensors go off; Terminate program with ERR104 if fault condition is detected
                    while not self.frontBeamBroken:
                        if self.rollerMotorVelocity >= 0:
                            jamReversalCount += 1
                            self.rollerMotor.set(-rollerVelocity)
                        elif jamReversalCount >= jamFaultThreshold:
                            os._exit(104)
                        pass #Gets rid of indentation error
