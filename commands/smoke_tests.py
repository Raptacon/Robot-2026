from typing import Callable
from constants import SwerveDriveConsts
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from wpimath.geometry import Rotation2d
# from subsystem.mechanisms.turret import Turret
from subsystem.intakeactions import IntakeSubsystem
from subsystem.ballpit import BallPitHopper
from subsystem.shooter import Shooter

from wpimath.kinematics import SwerveModuleState

import commands2
import wpilib
import rev
import time

class SmokeTests(commands2.SequentialCommandGroup):
    """    
    Smoke Tests for 2026 Bot.

    Tests are mostly created using commands2, and all are made
    upon initialization. For moving onto the next test, the
    "confirm" button from InputFactory is used. 

    This class tests the following: CAN Motor Feedback, 
    Movement and Angling of Swerve Modules, Movement 
    of Intake, Movement of Shooter
    """
    def __init__(self,
                drivetrain: SwerveDrivetrain,
                # velocity_vector_x: Callable[[], float]),
                # velocity_vector_y: Callable[[], float],
                # angular_velocity: Callable[[], float],
                # turret: Turret,
                intake: IntakeSubsystem,
                hopper: BallPitHopper,
                shooter: Shooter,
                ) -> None:
        """
        This creates the tests and all associated objects.

        Args:
            None

        Returns:
            None
        """
        super().__init__()

        self.drivetrain = drivetrain
        # self.turret = turret
        self.intake = intake
        self.hopper = hopper
        self.shooter = shooter

        self.allMotors = [self.shooter.feedMotor, self.shooter.leadFlywheelMotor, self.shooter.followerFlywheelMotor, self.intake.rollerMotor, self.intake.pivotMotor]
        self.testResults = []
        self.failedtests = False
        currentMotor = 0
        possibleUnpluggedCanBus = False
        dontskiptests = False

        self.progress = False
        self.testMessage = ""
        self.totaltests = 32 + len(self.allMotors)
        self.testNumber = 0
        # self.velocity_vector_x = velocity_vector_x
        # self.velocity_vector_y = velocity_vector_y
        # self.angular_velocity = angular_velocity

        # Test all Motors for feedback
        self.setElapsedTime()
        while currentMotor <= len(self.allMotors)-1:
            if possibleUnpluggedCanBus == True and currentMotor <= len(self.allMotors) - 2:
                if not dontskiptests:
                    self.testResults.append(">")
            else:
                self.allMotors[currentMotor].set(0)
                self.allMotors[currentMotor].getFaults()
                self.allMotors[currentMotor].getStickyFaults()
                time.sleep(0.2)

                if str(self.allMotors[currentMotor].getLastError()) == str(rev.REVLibError.kOk):
                    self.testResults.append(".")
                    if possibleUnpluggedCanBus:
                        if not dontskiptests:
                            currentMotor = 2
                            possibleUnpluggedCanBus = False
                else:
                    self.testResults.append("F")
                    if currentMotor == 0:
                        if not dontskiptests:
                            possibleUnpluggedCanBus = True
            self.setMessage("Motor Feedback", ("".join(self.testResults)))
            self.updateMessage()
            currentMotor += 1
        if self.testResults.count("F") != 0:
            self.failedtests = True
            if possibleUnpluggedCanBus == True:
                self.resultsMessage(F"{self.testResults.count(".")} passed, {self.testResults.count("F")} failed, {self.testResults.count(">")} skipped in {self.getElapsedTime()}s",
                                    "Not all Motor Tests succeded. This is usually due to an issue with communicating with motors.",
                                    "Did you plug in the CanBus?")
            else:
                self.resultsMessage(F"{self.testResults.count(".")} passed, {self.testResults.count("F")} failed, {self.testResults.count(">")} skipped in {self.getElapsedTime()}s",
                                    "Not all Motor Tests succeded. This is usually due to an issue with communicating with motors."
                                    )
        else:
            self.resultsMessage(F"{self.testResults.count(".")} passed, {self.testResults.count("F")} failed, {self.testResults.count(">")} skipped in {self.getElapsedTime()}s",
                            "All tests succeeded. Press confirm button to move onto manual tests.")
        self.addCommands(
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False))
        )
        if self.failedtests:
            self.addCommands(
                commands2.InstantCommand(lambda: self.resultsMessage(F"{self.testResults.count(".")} passed, {self.testResults.count("F")} failed, {self.testResults.count(">")} skipped in {self.getElapsedTime()}s",
                                    self.motorResults(self.allMotors),
                                    "To test anyway, press the Start Button."))
            )
        
        self.addRequirements(self.drivetrain)
        # Tests Swerve Modules (0-20)
        for index, swerve_module in enumerate(self.drivetrain.swerve_modules):
            if index == 0:
                self.addCommands(
                    commands2.cmd.runOnce(lambda: self.setMessage(0)),
                    commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)))
            self.addCommands(
                # Current swerve module's drive motor moves forward 0.2 meters per second until driver confirms 
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0.2, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda swerve_module=swerve_module:self.setMessage(str(swerve_module.getName()), "Check to see if module starts driving...", "Test confirms when Start Button is pressed")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's drive motor stops
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda swerve_module=swerve_module:self.setMessage(str(swerve_module.getName()), "Check to see if module stops driving...", "Test confirms when Start Button is pressed")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 0 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda swerve_module=swerve_module:self.setMessage(str(swerve_module.getName()), "Check to see if module rotates facing 0 degrees...", "Test confirms when Start Button is pressed")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 45 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(45)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda swerve_module=swerve_module:self.setMessage(str(swerve_module.getName()), "Check to see if module rotates facing 45 degrees...", "Test confirms when Start Button is pressed")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates to 90 degrees and driver confirms
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(90)), apply_cosine_scaling=False),
                                        self.drivetrain),
                commands2.cmd.runOnce(lambda swerve_module=swerve_module:self.setMessage(str(swerve_module.getName()), "Check to see if module rotates facing 90 degrees...", "Test confirms when Start Button is pressed")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
                # Current swerve module's steer motor rotates back to 0 degrees when finished
                commands2.InstantCommand(lambda swerve_module=swerve_module: swerve_module.set_state(SwerveModuleState(0, Rotation2d.fromDegrees(0)), apply_cosine_scaling=False),
                                        self.drivetrain)
            )
        # self.addRequirements(turret)
        self.addRequirements(intake)
        self.addRequirements(hopper)
        self.addRequirements(shooter)
        # Test Onboard Sensors (21-24)
        # self.addCommands(
            # Test confirms after Feed sensor activation
            # commands2.runOnce(lambda: self.setMessage(21, "Onboard Sensors", "Trigger Breakbeam Sensors at Feed", "Successful Activation of Feed Breakbeam Sensors")),
            # commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            # Test confirms after Intake sensor activation
            # commands2.cmd.runOnce(lambda: self.setMessage("Onboard Sensors", "Trigger Hall-Effects Sensor at Intake", "Successful Activation of Intake Hall-Effects Sensor")),
            # commands2.WaitUntilCommand(lambda: intake.HallEffectSensor.get()),
            # Test confirms after Turret sensor activation
            # commands2.runOnce(lambda: self.setMessage(23, "Onboard Sensors", "Trigger Forward Hall-Effects Sensor at Turret", "Successful Activation of Turret Forward Hall-Effects Sensor")),
            # commands2.WaitUntilCommand(lambda: turret.motor.getForwardLimitSwitch().get()),
            # commands2.runOnce(lambda: self.setMessage(24, "Onboard Sensors", "Trigger Reverse Hall-Effects Sensor at Turret", "Successful Activation of Turret Reverse Hall-Effects Sensor")),
            # commands2.WaitUntilCommand(lambda: turret.motor.getReverseLimitSwitch().get()),
        # )
        # Test Components (25-)
        self.addCommands(
            #Test Intake Deployment
            commands2.InstantCommand(lambda intake=intake: intake.deployIntake(), self.intake),
            commands2.cmd.runOnce(lambda: self.setMessage("Intake", "Check to see if Intake begins deploying...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Intake Stow
            commands2.InstantCommand(lambda intake=intake: intake.stowIntake(), self.intake),
            commands2.cmd.runOnce(lambda: self.setMessage("Intake", "Check to see if Intake begins stowing...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Hopper Activation
            commands2.InstantCommand(lambda hopper=hopper: hopper.setHexShaftSpeed(0.2), self.hopper),
            commands2.cmd.runOnce(lambda: self.setMessage("Hopper", "Check to see if Hopper activates...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda hopper=hopper: hopper.zeroHopperVelocity(), self.hopper),
            #Test Shooter Feed Activation
            commands2.InstantCommand(lambda shooter=shooter: shooter.toggleFeedActive(), self.shooter),
            commands2.cmd.runOnce(lambda: self.setMessage("Shooter", "Check to see if Feed activates...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda shooter=shooter: shooter.toggleFeedActive(), self.shooter),
            #Test Shooter Flywheel Activation
            commands2.InstantCommand(lambda shooter=shooter: shooter.setRPM(3000), self.shooter),
            commands2.cmd.runOnce(lambda: self.setMessage("Shooter", "Check to see if BOTH Flywheels activate...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda shooter=shooter: shooter.setRPM(0), self.shooter),
            #Test Vision
            #Test LEDs
            #Test NavX?
            commands2.cmd.runOnce(lambda: self.setMessage("NavX", "Rotate the Bot 90 Degrees", "Test confirms if NavX registers 90 degree rotation")),
        )

    # def execute(self):
    #     self.drivetrain.swerve_modules[0].set_state(SwerveModuleState(0.2, Rotation2d.fromDegrees(0)))

    def advance(self, progress: bool = True) -> None:
        """
        This will tell the code whether it should "advance" to the next test.
        
        Args:
            progress: whether code should advance to next test
        
        Returns:
            None
        """
        self.progress = progress

    def setMessage(self, testComponent: str = "", row1: str = "", row2: str = "", test: bool = True) -> None:
        """
        Sets the Test Message for Drivers.

        This will set the message for drivers running tests, and 
        is used for the code to communicate to drivers. Messages 
        are updated through Network Tables, and if Test is True, 
        then the current test number displayed at beginning of 
        message will increase.

        Args:
            testComponent: the component currently being tested
            row1: first row of message
            row2: second row of message
            test: whether message is being set as part of a test

        Returns:
            None
        """
        if test:
            self.testNumber += 1
        if self.testNumber == 0:
            self.testMessage = F"""{self.testNumber}/{self.totaltests}:\nBeginning of tests.
            \nPress start button when expected outcome is satisfied to move onto next test."""
        else:
            self.testMessage = F"""{self.testNumber}/{self.totaltests}:\nTesting {testComponent}...
            \n{row1}
            \n{row2}
            """
        print(self.testMessage)

    def resultsMessage(self, title: str = "", row1: str = "", row2: str = "", row3: str = "") -> None:
        """
        Sets the Results Message for Drivers.

        Drivers will see this message should the tests 
        pass/fail, used for the code to communicate to 
        drivers exactly what went wrong. Messages are 
        updated through Network Tables.

        Args:
            title: the title of the message
            row1: first row of message
            row2: second row of message
        """
        self.testMessage = F"""{title}
        \n{row1}
        \n{row2}
        \n{row3}
        """
        print(self.testMessage)
        
    def motorResults(self, motorsToReturn: list):
        """
        Returns the status of all inputted motors.
        
        Motor Statuses can go something like 
        'RevLibError.kOk' or 'RevLibError.kTimeout.' 
        Whatever the motor status is, this method
        will take it for each motor and bundle it 
        in a fasion such as "Motor Name: Motor 
        Status." Each motor is seperated by a 
        newline.
        
        Args:
            motorsToReturn: the motors to return statuses of
            
        Returns:
            Statuses of all inputted motors seperated by newline
        """
        message = ""
        for motors in motorsToReturn:
            message = str(motorsToReturn[motors]) + ": " + str(motorsToReturn[motors].getLastError()) + "\n"
        return message
        

    def setElapsedTime(self) -> None:
        """
        This sets the elapsed starting time for tests.

        Args:
            None
        
        Returns:
            None
        """
        self.timer = time.perf_counter()

    def getElapsedTime(self) -> float:
        """
        Returns amount of elapsed time since setElapsedTime() has been invoked.
        
        Args:
            None

        Returns:
            Time in seconds rounded to nearest hundredth
        """
        return round(time.perf_counter() - self.timer, 2)

    def updateMessage(self) -> None:
        """
        Updates the Message which has been set elsewhere into a Network Table.

        Args:
            None

        Returns:
            None
        """
        wpilib.SmartDashboard.putString("Test Message", self.testMessage)