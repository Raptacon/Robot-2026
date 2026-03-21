# Native imports
import math
from typing import Callable

# Internal imports
from constants import SwerveDriveConsts
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain

# Third-party imports
import commands2

class DefaultDrive(commands2.Command):
    """
    Base command to drive a swerve drive robot using an Xbox controller. This should
    be given as the default command for the swerve drivetrain subsystem.
    """
    def __init__ (
        self,
        drivetrain: SwerveDrivetrain,
        velocity_vector_x: Callable[[], float],
        velocity_vector_y: Callable[[], float],
        angular_velocity: Callable[[], float],
        field: Callable[[], bool]
    ) -> None:
        """
        Store joystick and button inputs within the object, and require the swerve drivetrain
        subsystem when executing this command.

        Args:
            drivetrain: the swerve drivetrain subsystem that this command with operate
            velocity_vector_x: live poll of the percentage of max translation velocity that the
                drivetrain should go in the X (+ forward-backward -) direction. Has
                domain [-1, 1]
            velocity_vector_y: live poll of the percentage of max translation velocity that the
                drivetrain should go in the Y (+ left-right -) direction. Has
                domain [-1, 1]
            angular_velocity: live poll of the percentage of max angular velocity that the drivetrain
                should go in CCW direction. Has domain [-1, 1]
            field: live poll. if True, the drivetrain should move in field relative mode. If False,
                the robot should move in robot relative mode

        Returns:
            None: class initialization executed upon construction
        """
        super().__init__()

        self.drivetrain = drivetrain
        self.velocity_vector_x = velocity_vector_x
        self.velocity_vector_y = velocity_vector_y
        self.angular_velocity = angular_velocity
        self.field = field
        self.addRequirements(self.drivetrain)

    def execute(self) -> None:
        """
        Take the controller input poll functions and transform them into inputs for the
        swerve drivetrain's drive interface. Execute drive functionality using those inputs.

        Returns:
            None: interface eventually passes desired goal states to the swerve modules
        """
        self.drivetrain.drive(
            self.velocity_vector_x() * SwerveDriveConsts.maxTranslationMPS,
            self.velocity_vector_y() * SwerveDriveConsts.maxTranslationMPS,
            self.angular_velocity() * math.radians(SwerveDriveConsts.maxAngularDPS),
            self.field()
        )
