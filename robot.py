#!/usr/bin/env python3

import typing
import inspect
import commands2

from robotswerve import RobotSwerve
from utils.datalog_bridge import setup_logging
from utils.loop_timing import LoopTimer
import wpilib
import logging


class MyRobot(commands2.TimedCommandRobot):
    """
    Our default robot class, pass it to wpilib.run
    Command v2 robots are encouraged to inherit from TimedCommandRobot, which
    has an implementation of (self) -> None:
    which runs the scheduler for you
    """
    # 20 ms default period (50 Hz)
    kDefaultPeriod: typing.ClassVar[float] = 20.0
    autonomousCommand: typing.Optional[commands2.Command] = None

    def __init__(self) -> None:

        self.__errorLogged = False
        self.__lastError = None
        self.__errorCaughtCount = 0

        self.__initFrameTiming()

        # Bridge Python logging -> wpilog + NT-controlled log level
        setup_logging()

        # setup our scheduling period. Defaulting to 20 Hz (50 ms)
        super().__init__(period=MyRobot.kDefaultPeriod / 1000)
        # Instantiate our RobotContainer. This will perform all our button bindings, and put our
        # autonomous chooser on the dashboard.
        if not hasattr(self, "container"):
            # to work around sim creating motors during tests, assign to class and if already created keep using created robot class for tests.
            # during robot running, this is only every called once
            MyRobot.container = RobotSwerve(lambda: self.isDisabled)

    def robotInit(self) -> None:
        """
        This function is run when the robot is first started up and should be used for any
        initialization code.
        """

    def robotPeriodic(self) -> None:
        self.__callAndCatch(self.container.robotPeriodic)

        wpilib.SmartDashboard.putNumber("Code Crash Count", self.__errorCaughtCount)
        self.__frameTimingPeriodic()

    def disabledInit(self) -> None:
        """This function is called once each time the robot enters Disabled mode."""
        self.__timing.reset_all()
        self.container.disabledInit()

    def disabledPeriodic(self) -> None:
        """This function is called periodically when disabled"""
        self.__timing.start("userCode")
        self.container.disabledPeriodic()

    def autonomousInit(self) -> None:
        """This autonomous runs the autonomous command selected by your RobotContainer class."""
        self.__timing.reset_all()
        self.container.autonomousInit()

    def autonomousPeriodic(self) -> None:
        """This function is called periodically during autonomous"""
        self.__timing.start("userCode")
        self.__callAndCatch(self.container.autonomousPeriodic)

    def teleopInit(self) -> None:
        self.__timing.reset_all()
        self.container.teleopInit()

    def teleopPeriodic(self) -> None:
        """This function is called periodically during operator control"""
        self.__timing.start("userCode")
        self.__callAndCatch(self.container.teleopPeriodic)

    def testInit(self) -> None:
        self.__timing.reset_all()
        self.container.testInit()

    def testPeriodic(self) -> None:
        self.__timing.start("userCode")
        self.container.testPeriodic()

    def getRobot(self) -> RobotSwerve:
        return self.container

    def __initFrameTiming(self):
        """Set up loop timing instrumentation.

        Wraps CommandScheduler.run() BEFORE super().__init__() captures it
        so the scheduler channel measures the real execution cost.
        """
        self.__timing = LoopTimer(budget_sec=MyRobot.kDefaultPeriod / 1000)
        self.__timing.add_channel("userCode")
        self.__timing.add_channel("scheduler")

        scheduler = commands2.CommandScheduler.getInstance()
        original_run = scheduler.run
        timing = self.__timing

        def _timed_run():
            timing.start("scheduler")
            original_run()
            timing.stop("scheduler")

        scheduler.run = _timed_run

    def __frameTimingPeriodic(self):
        """Stop the userCode channel and publish all timing stats."""
        self.__timing.stop("userCode")
        self.__timing.publish()

    def __callAndCatch(self, func: typing.Callable[[], None]) -> None:
        try:
            #Invoke the function
            func()

            #if we returned, it didnt crash so clear the last error if it was set
            if self.__errorLogged and self.__lastError is not None:
                logging.info(f"Logged error cleared for: {str(self.__lastError)}")
                self.__errorLogged = False
                self.__lastError = None
        except Exception as e:
            self.__lastError = e
            name = inspect.currentframe().f_back.f_code.co_name
            if self.isSimulation():
                raise e

            self.__errorCaughtCount = self.__errorCaughtCount + 1

            if not self.__errorLogged:
                logging.exception(f"(CRASH CATCH) {name} error: ")
                self.__errorLogged = True


if __name__ == "__main__":
    print("Please run python -m robotpy <args>")
    exit(1)
