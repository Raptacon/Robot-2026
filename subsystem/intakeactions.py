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

        self.HallEffectSensor = not wpilib.DigitalInput(6)

        #Set Variables
        self.intakeStowed = 0 #Maximum amount of rotations before assuming intake is deployed
        self.intakeFaultThreshold = 20 #Amount of time spent trying to deploy/stow intake before fault condition is triggered
        self.intakeMagnetFaultThreshold = 2 #Amount of time required for magnet to stop tripping hall effects sensors before fault condition is triggered
        self.rollerFaultThreshold = 20 #Amount of time spent trying to operate rollers before fault condition is triggered
        self.jamTime = 3 #Amount of time to wait before assuming a ball inside the intake has gotten stuck
        self.jamFaultThreshold = 0 #Amount of attempts done trying to reverse rollers in the event of a jam before a fault condition is triggered
        self.rollerDuration = 50 #Amount of rotations before stopping Roller Motor

        self.intakeVelocity = 0 #Leave at 0 - any updating is to be done thru Network Table, Speed (in rpm) in which the intake motor will move upon deployment/stowing
        self.rollerVelocity = 0 #Leave at 0 - any updating is to be done thru Network Table, Speed in which the roller motor will move upon deployment
        self.intakeDeployed = 200 #Leave at 200 - it's a starting value - Hall Effect Sensor determines actual minimum amount of rotations before assuming intake is deployed
        self.baselineFault = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.rollerOccurence = 0 #Leave at 0, provides reference for timed roller activation
        self.intakeCondition = 0 #Leave at 0, provides reference for intake fault detection
        self.rollerStop = 0 #Leave at 0, stores amount of rotations to stop at during timed roller activation
        self.baselineJam = 0 #Leave at 0, provides baseline to compare to when determining faults
        self.jamReversalCount = 0 #Leave at 0, stores amount of attempts in reversing motors in the event of a jam before a fault condition is triggered

    def deployIntake(self):
        #Check Sensor for deployment, if not, deploy it.
        if self.intakeCondition <= 0:
                self.baselineFault = time.perf_counter()
                self.intakeCondition = 1
        if self.intakeCondition == 1:
            if self.HallEffectSensor.get() == True:
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
            self.baselineFault = time.perf_counter()
            
            self.rollerMotor.set(self.rollerVelocity)
            if self.baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                print("INTAKE ERR103: Activation of roller doesn't appear to be working! Stopping code.")
                os._exit(103)

    def deactivateRoller(self):
        if self.hasSecondMotor:
            self.baselineFault = time.perf_counter()
        
            self.rollerMotor.set(0)
            if self.baselineFault - time.perf_counter() >= self.rollerFaultThreshold:
                print("INTAKE ERR104: Deactivation of roller doesn't appear to be working! Stopping code.")
                os._exit(104)

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
        if self.intakeCondition >= 0:
                self.baselineFault = time.perf_counter()
                self.intakeCondition = -1
        if self.intakeCondition == -1:
            if self.intakeMotorEncoder.getPosition() <= self.intakeStowed:
                self.intakeCondition = 0
            if self.baselineFault - time.perf_counter() >= self.intakeFaultThreshold:
                print("INTAKE ERR102: Intake stow doesn't appear to be working! Stopping code.")
                os._exit(102)
            if self.intakeMagnetFaultThreshold + 1 >= time.perf_counter() - self.baselineFault >= self.intakeMagnetFaultThreshold:
                if self.HallEffectSensor.get() == True:
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
            
                        while not self.frontBeamBroken:
                            if self.rollerMotorVelocity >= 0:
                                jamReversalCount += 1
                                self.rollerMotor.set(-self.rollerVelocity)
                            elif jamReversalCount >= self.jamFaultThreshold:
                                print("INTAKE ERR104: Motor reversal as a result of jam does not appear to be working! Stopping code.")
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