# Native imports
from math import inf, pi
from typing import Callable

# Internal imports
from config import OperatorRobotConfig
from constants import SwerveDriveConsts
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain

# Third-party imports
from commands2 import Command
from wpimath import applyDeadband
from wpimath.controller import ProfiledPIDController
from wpimath.geometry import Rotation2d, Translation2d
from wpimath.kinematics import ChassisSpeeds
from wpimath.trajectory import TrapezoidProfile


class PIDAlignToTarget(Command):
    def __init__(
        self,
        drivetrain: SwerveDrivetrain,
        target_location: Callable[[], Translation2d] | None,
        velocity_vector_x: Callable[[], float],
        velocity_vector_y: Callable[[], float],
        field: Callable[[], bool],
        rotation_pid_config: tuple = OperatorRobotConfig.pid_to_pose_rotation_pid_profile,
        setpoint_tolerances: tuple = OperatorRobotConfig.pid_to_pose_setpoint_tolerances,
        alignment_angle: Rotation2d = Rotation2d.fromDegrees(0)
    ) -> None:
        """
        Align rotationally to a target location using PID. In this control system, the objective function is the
        absolute error between the current and goal omega value. This objective function is minimized
        until rotational error is within a given tolerance. The decision variable of the control system
        is rotational velocity of the drivetrain. The contraint is a trapezoidal motion profile for
        rotational motion, where slopes represent max acceleration and the plateaus represent max
        velocity.

        Note that the robot will rotate to the target orientation as quickly as possible.

        Args:
            drivetrain: the drivetrain subsystem that effects movement from current rotation to target rotation
            target_location: the desired always-blue location to which the robot's heading should align
            velocity_vector_x: live poll of the percentage of max translation velocity that the
                drivetrain should go in the X (+ forward-backward -) direction. Has
                domain [-1, 1]
            velocity_vector_y: live poll of the percentage of max translation velocity that the
                drivetrain should go in the Y (+ left-right -) direction. Has
                domain [-1, 1]
            field: live poll. if True, the drivetrain should move in field relative mode. If False,
                the robot should move in robot relative mode
            rotation_pid_config: the PID and trapezoidal profile constants for rotational motion
            setpoint_tolerances: the threshold for omega below which absolute
                rotational error is low enough for the robot to be considered arrived at the target rotation
            alignment_angle: which angle, CCW positive, offset the robot's base heading to align
                with the target

        Returns:
            None: class initialization executed upon construction
        """
        super().__init__()

        self.drivetrain = drivetrain
        self.target_location = target_location
        self.velocity_vector_x = velocity_vector_x
        self.velocity_vector_y = velocity_vector_y
        self.field = field
        self.rotation_pid = ProfiledPIDController(
            *rotation_pid_config[0:3], TrapezoidProfile.Constraints(*rotation_pid_config[3:5])
        )
        self.alignment_angle = alignment_angle

        self.rotation_pid.enableContinuousInput(-pi, pi)
        self.rotation_pid.setTolerance(setpoint_tolerances[2])

        self.target_rotation = None

        self.addRequirements(self.drivetrain)

    def execute(self) -> None:
        """
        If a target rotation is available, run the profiled PID control system to move from the
        current rotation to the target rotation. When no target is available, pass through
        driver translation inputs with zero rotation so the drivetrain is not left uncontrolled.

        Returns:
            None: translational and rotational velocities are passed into the drivetrain's drive
                method, which runs the motors accordingly
        """
        target = self.target_location() if self.target_location else None
        if target is None:
            self.target_rotation = None
            self.drivetrain.drive(
                self.velocity_vector_x() * SwerveDriveConsts.maxTranslationMPS,
                self.velocity_vector_y() * SwerveDriveConsts.maxTranslationMPS,
                0,
                self.field()
            )
            return

        self.target_rotation = (target - self.drivetrain.current_pose().translation()).angle()
        current_rotation = self.drivetrain.current_pose().rotation()
        offset_current_rotation = current_rotation + self.alignment_angle

        rotation_error = (self.target_rotation - offset_current_rotation).radians()
        rotation_output = -applyDeadband(self.rotation_pid.calculate(rotation_error, 0), 0.04, inf)

        new_rotation_velocity = ChassisSpeeds.fromFieldRelativeSpeeds(0, 0, rotation_output, current_rotation)
        self.drivetrain.drive(
            self.velocity_vector_x() * SwerveDriveConsts.maxTranslationMPS,
            self.velocity_vector_y() * SwerveDriveConsts.maxTranslationMPS,
            new_rotation_velocity.omega,
            self.field()
        )

    def end(self, interrupted: bool) -> None:
        """
        When this command is over, have the robot stop driving (set all velocities to zero).

        Args:
            interrupted: whether the command was terminated by way of interruption

        Returns:
            None: drivetrain subsystem will apply zeroed velocities to motors
        """
        self.drivetrain.stop_driving(apply_to_modules=True)

    def isFinished(self) -> bool:
        """
        The command is considered complete when the absolute error of each coodinate is within tolerance.
        If there is no target rotation for the robot to navigate to, this command instantly ends.

        Returns:
            True if the command is complete according to the definition above, False otherwise.
        """
        at_setpoints = self.rotation_pid.atSetpoint()
        no_target = self.target_rotation is None
        return at_setpoints or no_target
