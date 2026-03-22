# Native imports
from math import inf, pi
from typing import Callable

# Internal imports
from config import OperatorRobotConfig
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain

# Third-party imports
from commands2 import Command
from wpimath import applyDeadband
from wpimath.controller import ProfiledPIDController
from wpimath.geometry import Rotation2d
from wpimath.kinematics import ChassisSpeeds
from wpimath.trajectory import TrapezoidProfile


class PIDToAngle(Command):
    def __init__(
        self,
        drivetrain: SwerveDrivetrain,
        target_rotation: Callable[[], Rotation2d] | None,
        rotation_pid_config: tuple = OperatorRobotConfig.pid_to_pose_rotation_pid_profile,
        setpoint_tolerances: tuple = OperatorRobotConfig.pid_to_pose_setpoint_tolerances
    ) -> None:
        """
        Align to a target rotation using PID. In this control system, the objective function is the
        absolute error between the current and goal x, y, and omega coordinates, separately. This
        objective function is minimized until all errors are within a given tolerance. The decision
        variables of the control system are the translational and rotational velocities of the
        drivetrain. The contraints are a trapezoidal motion profiles for translational and rotational
        motion, where slopes represent max acceleration and the plateaus represent max velocity.

        Note that the robot will rotate to the target orientation as quickly as possible.

        Args:
            drivetrain: the drivetrain subsystem that effects movement from current rotation to target rotation
            target_rotation: the desired always-blue orientation of the robot
            rotation_pid_config: the PID and trapezoidal profile constants for rotational motion
            setpoint_tolerances: the threshold for omega below which absolute
                rotational error is low enough for the robot to be considered arrived at the target rotation

        Returns:
            None: class initialization executed upon construction
        """
        super().__init__()

        self.drivetrain = drivetrain
        self.target_rotation = target_rotation
        self.rotation_pid = ProfiledPIDController(
            *rotation_pid_config[0:3], TrapezoidProfile.Constraints(*rotation_pid_config[3:5])
        )

        self.rotation_pid.enableContinuousInput(-pi, pi)
        self.rotation_pid.setTolerance(setpoint_tolerances[2])

        self.addRequirements(self.drivetrain)

    def execute(self) -> None:
        """
        If a target rotation is available, run the profiled PID control system to move from the
        current rotation to the target rotation.

        Returns:
            None: translational and rotational velocities are passed into the drivetrain's drive
                method, which runs the motors accordingly
        """
        if self.target_rotation:
            current_rotation = self.drivetrain.current_pose().rotation()
            
            rotation_error = (self.target_rotation() - current_rotation).radians()
            rotation_output = -applyDeadband(self.rotation_pid.calculate(rotation_error, 0), 0.04, inf)

            drive_speed = ChassisSpeeds.fromFieldRelativeSpeeds(0, 0, rotation_output, current_rotation)
            self.drivetrain.drive(0, 0, drive_speed.omega, False)

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
        no_target_rotation = True if not self.target_rotation else False
        return at_setpoints or no_target_rotation
