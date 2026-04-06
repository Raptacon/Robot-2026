from typing import Callable
from constants import SwerveDriveConsts
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from wpimath.geometry import Rotation2d
# from subsystem.mechanisms.turret import Turret
from subsystem.intakeactions import IntakeSubsystem
from subsystem.ballpit import BallPitHopper
from subsystem.mechanisms.shooter.shooter import Shooter
from subsystem.mechanisms.shooter.hood import Hood
from subsystem.addressableLEDs import AddressableLEDs

from wpimath.kinematics import SwerveModuleState

import commands2
import wpilib
import rev
import time
import navx

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
                hood: Hood,
                led: AddressableLEDs,
                navx: navx
                ) -> None:
        """
        This creates the tests and all associated objects.
        
        These include:
            - 8 Motor Communication Tests
            - 20 Drivetrain Tests
            - 9 Subsystem Tests

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
        self.hood = hood
        self.led = led
        self.navx = navx

        self.allMotors = [self.intake.rollerMotor, self.intake.pivotMotor, self.hopper.hopperMotor, 
                          self.shooter.leadFeedMotor, self.shooter.followerFeedMotor, self.shooter.leadFlywheelMotor, 
                          self.shooter.followerFlywheelMotor, self.hood.motor]
        self.motorNames = ["Intake - Roller Motor", "Intake - Pivot Motor", "Hopper - Hex Shaft Motor", 
                           "Shooter - Lead Feed Motor", "Shooter - Follower Feed Motor", "Shooter - Lead Flywheel Motor", 
                           "Shooter - Follower Flywheel Motor", "Shooter - Hood Motor"]
        self.testResults = []
        self.testPassFail = ""
        self.failedtests = False
        self.targetAngle = None

        currentMotor = 0

        self.progress = False
        self.testMessage = ""
        self.totaltests = 29 + len(self.allMotors)
        self.testNumber = 0
        # self.velocity_vector_x = velocity_vector_x
        # self.velocity_vector_y = velocity_vector_y
        # self.angular_velocity = angular_velocity
        
        # Test all Motors for feedback
        self.setElapsedTime()
        while currentMotor <= len(self.allMotors)-1:
            self.allMotors[currentMotor].set(0)
            self.allMotors[currentMotor].getFaults()
            self.allMotors[currentMotor].getStickyFaults()
            time.sleep(0.267)
            
            testMotor = self.allMotors[currentMotor]
            lastError = testMotor.getLastError()
            self.testResults.append(lastError.name)

            if self.testResults[-1] == "kOk":
                self.testPassFail = self.testPassFail + "."
            else:
                self.testPassFail = self.testPassFail + "F"
            self.setMessage("Motor Feedback", self.testPassFail)
            self.updateMessage()
            currentMotor += 1
        self.testDuration = self.getElapsedTime()
        if self.testPassFail.count('F') != 0:
            self.failedtests = True
            if self.testPassFail.count('.') == 0:
                self.resultsMessage(F"{self.testPassFail.count('.')} passed, {self.testPassFail.count('F')} failed, {self.testPassFail.count('>')} skipped in {self.testDuration}s",
                                    "Not all Motor Tests succeded. This is usually due to an issue with communicating with motors.",
                                    "Did you plug in the CanBus?")
            else:
                self.resultsMessage(F"{self.testPassFail.count('.')} passed, {self.testPassFail.count('F')} failed, {self.testPassFail.count('>')} skipped in {self.testDuration}s",
                                    "Not all Motor Tests succeded. This is usually due to an issue with communicating with motors."
                                    )
        else:
            self.resultsMessage(F"{self.testPassFail.count('.')} passed, {self.testPassFail.count('F')} failed, {self.testPassFail.count('>')} skipped in {self.testDuration}s",
                            "All Motor Communication tests succeeded. Press confirm button to move onto manual tests.")
        self.addCommands(
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False))
        )
        if self.failedtests:
            self.addCommands(
                commands2.InstantCommand(lambda: self.resultsMessage(F"{self.testPassFail.count('.')} passed, {self.testPassFail.count('F')} failed, {self.testPassFail.count('>')} skipped in {self.testDuration}s",
                                    self.splitResults(self.testResults, self.motorNames),
                                    "To test anyway, press the Start Button.")),
                commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False))
            )
        
        self.addRequirements(self.drivetrain)
        # Tests Swerve Modules
        for index, swerve_module in enumerate(self.drivetrain.swerve_modules):
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
        self.addRequirements(led)
        self.addRequirements(hood)

        # Test Onboard Sensor
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
        # Test Components
        self.addCommands(
            #Test Intake Deployment
            commands2.InstantCommand(lambda intake=intake: intake.deployIntake(), self.intake),
            commands2.cmd.runOnce(lambda: self.setMessage("Intake", "Check for Intake deployment...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Intake Roller Activation
            commands2.InstantCommand(lambda intake=intake: intake.requestRollerOn(), self.intake),
            commands2.cmd.runOnce(lambda: self.setMessage("Intake", "Check for activation of Intake Rollers...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda intake=intake: intake.requestRollerOff(), self.intake),
            #Test Intake Stow
            commands2.InstantCommand(lambda intake=intake: intake.stowIntake(), self.intake),
            commands2.cmd.runOnce(lambda: self.setMessage("Intake", "Check for Intake stow...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            #Test Hopper Activation
            commands2.InstantCommand(lambda hopper=hopper: hopper.setHexShaftSpeed(0.2), self.hopper),
            commands2.cmd.runOnce(lambda: self.setMessage("Hopper", "Check for Hopper activation...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda hopper=hopper: hopper.zeroHopperVelocity(), self.hopper),
            #Test Shooter Feed Activation
            commands2.InstantCommand(lambda shooter=shooter: shooter.toggleFeedActive(), self.shooter),
            commands2.cmd.runOnce(lambda: self.setMessage("Shooter", "Check for activation of BOTH Feed Motors...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda shooter=shooter: shooter.toggleFeedActive(), self.shooter),
            #Test Shooter Flywheel Activation
            commands2.InstantCommand(lambda shooter=shooter: shooter.setRPM(3000), self.shooter),
            commands2.cmd.runOnce(lambda: self.setMessage("Shooter", "Check for activation of BOTH flywheels...", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda shooter=shooter: shooter.setRPM(0), self.shooter),
            #Test Shooter Hood Activation
            commands2.InstantCommand(lambda hood=hood: hood.setAngleNormalized(1.0), self.hood),
            commands2.cmd.runOnce(lambda: self.setMessage("Shooter", "Check for extension of Hood", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda hood=hood: hood.setAngleNormalized(0.0), self.hood),
            #Test Vision
            #Test LEDs
            commands2.InstantCommand(lambda led=led: led.LEDConstantColor(wpilib.Color.kRed), self.led),
            commands2.cmd.runOnce(lambda: self.setMessage("LEDs", "Check for the lighting up of LEDs to Red", "Test confirms when Start Button is pressed")),
            commands2.WaitUntilCommand(lambda: self.progress).finallyDo(lambda _: self.advance(False)),
            commands2.InstantCommand(lambda led=led: led.LEDConstantColor(wpilib.Color.kBlack), self.led),
            #Test NavX
            commands2.cmd.runOnce(lambda: self.setMessage("NavX", "Rotate the Bot 90 Degrees", "Test confirms if NavX registers rotation")),
            commands2.WaitUntilCommand(lambda: self.angleTestNavX(90)),
        )

    def advance(self, progress: bool = True) -> None:
        """
        This will tell the code whether it should "advance" to the next test.
        
        Args:
            progress: whether code should advance to next test
        
        Returns:
            None
        """
        self.progress = progress
        
    def angleTestNavX(self, turnAmount: int) -> bool:
        """
        Tests angle detection with NavX
        
        When calling for the first time, the "angle baseline" is
        established, and for the function to return true, the
        NavX reading must read a certain amount of degrees higher
        than the angle baseline. This will be done by turning the
        bot until it satisifes the condition.
        
        If the robot is not turned enough, the function will
        return false.
        
        Args: 
            turnAmount: the amount of degrees to turn robot
        
        Returns:
            whether the robot has been turned the amount of degrees
        """
        
        if self.targetAngle is None:
            self.targetAngle == self.navx.getAngle() + turnAmount
        else:
            if self.navx.getAngle() >= self.targetAngle:
                self.targetAngle = None
                return True
            else:
                return False

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
        
    def splitResults(self, motorStatuses: list, motorNames: list) -> str:
        """
        Returns the status of all inputted motors.
        
        Motor Statuses can go something like 
        'kOk' or 'kTimeout.' This method will 
        take inputted motor statuses (in the 
        form of a list) and their associated 
        names, and will bundle them in an 
        "elegant fasion" ex: "Motor Name: kOk"
        
        Args:
            motorStatuses: statuses of the motors
            motorNames: names of the motors
            
        Returns:
            Inputted Motor Names, and their status seperated by newline
        """
        message = ""
        for index, motor in enumerate(motorStatuses):
            message = message + motorNames[int(index)] + ": " + motor + "\n"
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