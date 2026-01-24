import commands2
import phoenix5
import wpilib

from subsystem.intakeactions import IntakeSubsystem


class MyRobot(commands2.TimedCommandRobot):
    """
    We've created a "WestCoastRobot" class to express all of our robot code to
    WPILib. This class has a number of different methods, each representing
    different phases of booting up the robot and progressing through match gameplay.

    WPILib strongly follows object-oriented programming principles, and one such
    principle we see here is inheritance. "Inheritance" is when one class brings
    in the data attributes and methods of another. For example, if we make a
    class to represent a mammal and say that a mammal is warm-blooded, then when
    we make a class to represent a dog and inherit from the mammal class,
    the dog will also be warm blooded.

    Here, our robot class inherits from a generic timed robot class that we
    brought in from the commands2 part of the RobotPy ecosystem. Any robot
    built off of this timed robot class will execute code based on an internal
    clock that ticks on a fixed interval. We'll explore this more later when we
    start looking at autonomous routines.
    """
    def robotInit(self):
        """
        The code in robotInit is executed as soon as the robot is powered on or
        when new code is deployed. It is typically used to set up virtual
        representations of physical aspects of the robot, like motors, drivetrains,
        sensors, and much more!

        When creating instance attributes, we'll use self.<attribute_name>
        syntax, like self.a_specific_dog. This lets us create data elements within a specific object.
        """
        # This lets us cleanly refer to the functionality in the timed robot class
        super().__init__()

        MyRobot.intake = IntakeSubsystem()


    def disabledInit(self):
        """
        This code executes immediately when the robot is switched into its disabled
        state. When the robot is disabled, it should stop functioning and do
        nothing. This state is often used to ensure safety.
        """
        # "pass" is a Python keyword saying that we are doing nothing in this method
        pass

    def disabledPeriodic(self):
        """
        This code executes on every internal clock tick while the robot is in its
        disabled state. You can think of this as a time-spaced "while" loop that
        keeps running until the robot exists the disabled state. 
        """
        pass

    def autonomousInit(self):
        """
        This code executes immediately when the robot is switched into its autonomous
        state. When the robot is autonomous, it operates with absolutely zero human
        input. FRC matches often start with a 15-second autonomous period.

        The "init" autonomous method is often used to set up the starting positional
        parameters of the robot and provide a standard set of instructions.
        """

        pass

    def autonomousPeriodic(self):
        """
        This code executes on every internal clock tick while the robot is in its
        autonomous state. You can think of this as a time-spaced "while" loop that
        keeps running until the robot exists the autonomous state.

        The "periodic" autonomous method is often used to perform a sequence of
        specific operations as the robot progresses through its autonomous routine.
        """
        pass

    def teleopInit(self) -> None:
        """
        This code executes immediately when the robot is switched into its
        teleoperated state. When the robot is teleoperated, it operates according
        to explicit instructions given by a human driver. FRC matches often have
        a 2 minute and 15 second teleoperated period.

        
        The "init" teleoperated method is often used to provide a standard
        instruction interface for a select choice of robot mechanisms.
        """
        


        pass

    def teleopPeriodic(self):
        """
        This code executes on every internal clock tick while the robot is in its
        teleoperated state. You can think of this as a time-spaced "while" loop that
        keeps running until the robot exists the teleoperated state.

        The "periodic" teleoperated method is often used perform specific manuevers
        with the drivetrain and/or to actuate our mechanisms.
        """
        
        self.intake.activateRoller();
    

        # ***

    def testInit(self):
        """
        The test state is used to debug a specific block of code. We use this
        to try out some new code that we've written while avoiding conflicts
        with the existing code in the other state methods.
        """
        pass

    def testPeriodic(self):
        """
        The test state is used to debug a specific block of code. We use this
        to try out some new code that we've written while avoiding conflicts
        with the existing code in the other state methods.
        """
        pass


# This is fancy Python syntax telling the interpreter to run the indented code block
# when executing this script.

# If you're familiar with the "main" file in Java, this code effectively makes
# this .py script the "main" file of our program
if __name__ == "__main__":
    # WPILib will operate the robot according to the logic we defined in our class
    wpilib.run(WestCoastRobot)
