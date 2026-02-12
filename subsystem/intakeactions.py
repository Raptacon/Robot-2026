import wpilib
import commands2
import rev
import time
import os
import ntcore

from constants import CaptainPlanetConsts as intakeConsts

intakeVelocity = 0.3 #Speed (in rpm) in which the intake motor will move upon deployment/stowing
intakeMotorThreshold = 1 #Used to determine whether or not intake is deployed
intakeFaultThreshold = 10 #Amount of time spent trying to deploy/stow intake before fault condition is triggered
rollerVelocity = 0.3 #Speed in which the roller motor will move upon deployment
rollerFaultThreshold = 10 #Amount of time spent trying to operate rollers before fault condition is triggered
jamTime = 3 #Amount of time to wait before assuming a ball inside the intake has gotten stuck
jamFaultThreshold = 10 #Amount of attempts done trying to reverse rollers in the event of a jam before a fault condition is triggered

baselineFault = 0 #Leave at 0, provides baseline to compare to when determining faults
baselineJam = 0 #Leave at 0, provides baseline to compare to when determining faults
jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered

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
            self.rollerMotorVelocity = self.rollerMotorEncoder.getVelocity()

        #Initialize Break Beams
        self.frontBreakbeam = wpilib.DigitalInput(intakeConsts.kFrontBreakBeam)
        self.backBreakbeam = wpilib.DigitalInput(intakeConsts.kBackBreakBeam)
        self.frontBeamBroken = not self.frontBreakbeam.get()
        self.backBeamBroken = not self.backBreakbeam.get()

        self.HallEffectSensor = not wpilib.DigitalInput(6)

        #Set Variables
        self.intakeDeployed = 200 #Minimum amount of rotations before assuming intake is deployed
        self.intakeStowed = 0 #Maximum amount of rotations before assuming intake is stowed
        self.intakeFaultThreshold = 2 #Amount of time spent trying to deploy/stow intake before fault condition is triggered
        self.rollerFaultThreshold = 2 #Amount of time spent trying to operate rollers before fault condition is triggered
        self.jamTime = 3 #Amount of time to wait before assuming a ball inside the intake has gotten stuck
        self.jamFaultThreshold = 0 #Amount of attempts done trying to reverse rollers in the event of a jam before a fault condition is triggered
        self.intakeMagnetFaultThreshold = 2

        self.intakeCondition = 0
        self.intakeVelocity = 0 #Leave at zero - any updating is to be done thru Network Table, Speed (in rpm) in which the intake motor will move upon deployment/stowing
        self.rollerVelocity = 0 #Leave at zero - any updating is to be done thru Network Table, Speed in which the roller motor will move upon deployment
        self.baselineFault = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.baselineJam = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered

    def deployIntake(self):
        #Check Sensor for deployment, if not, deploy it.
        if self.intakeCondition <= 0 and self.intakeMotorEncoder.getPosition() <= self.intakeDeployed:
                self.baselineFault = time.perf_counter()
                self.intakeCondition = 1
        if self.intakeCondition == 1:
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
            self.rollerMotor.set(self.rollerVelocity)
                #if baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                    #os._exit(103)

    def deactivateRoller(self):
        #if self.hasSecondMotor:
            #self.baselineFault = time.perf_counter()
        
            #Try to terminate voltage until motor stops moving; Terminate program with ERR103 if fault condition is detected
            #while self.rollerMotorEncoder.getVelocity() != 0:
        self.rollerMotor.set(0)
                #if baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                    #os._exit(103)

    def stowIntake(self):
        if self.intakeCondition >= 0 and self.intakeMotorEncoder.getPosition() >= self.intakeStowed:
                self.baselineFault = time.perf_counter()
                self.intakeCondition = -1
        if self.intakeCondition == -1:
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
            if self.frontBeamBroken:
                baselineJam = time.perf_counter()
                while not self.backBeamBroken:
                    #If Ball appears to have jammed, reverse rollers
                    if self.baselineFault - time.perf_counter >= self.rollerFaultThreshold:
                        self.baselineFault = time.perf_counter()
            
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

    def motorChecks(self):
        if self.intakeMotorEncoder.getPosition() >= self.intakeDeployed + 15 and self.intakeCondition == 1:
            print("INTAKE ERR121: Intake Motor appears to be deploying outside of limits! Stopping Code.")
            os._exit(121)
        if self.intakeMotorEncoder.getPosition() <= self.intakeStowed - 15 and self.intakeCondition == -1:
            print("INTAKE ERR122: Intake Motor appears to be stowing outside of limits! Stopping Code.")
            os._exit(122)
        if self.intakeMotorEncoder.getPosition() >= self.intakeDeployed and self.intakeCondition == 1:
            self.intakeCondition = 0
        if self.intakeMotorEncoder.getPosition() <= self.intakeStowed and self.intakeCondition == -1:
            self.intakeCondition = 0

        if self.intakeCondition == 0:
            self.intakeVelocity = 0
        self.intakeMotor.set(self.intakeCondition * self.intakeVelocity)

    def periodic(self):
        wpilib.SmartDashboard.putNumber("Intake Position", self.intakeMotorEncoder.getPosition())
        wpilib.SmartDashboard.putNumber("Roller Position", self.rollerMotorEncoder.getPosition())
        wpilib.SmartDashboard.putNumber("Intake Deployed", self.intakeDeployed)
        wpilib.SmartDashboard.putBoolean("Hall Effects Sensor", self.HallEffectSensor.get())
        wpilib.SmartDashboard.putNumber("Time", time.perf_counter())
        wpilib.SmartDashboard.putNumber("Baseline Fault", self.baselineFault)
        wpilib.SmartDashboard.putNumber("Intake Condition", self.intakeCondition)
        
        self.motorChecks()

        self.motorChecks()