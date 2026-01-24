# Native imports
from typing import Tuple

# Internal imports
from config import OperatorRobotConfig
from constants import SwerveDriveConsts
from .swerve_module import SwerveModuleMk4iSparkMaxNeoCanCoder

# Third-party imports
import navx
from commands2 import Subsystem
from pathplannerlib.auto import AutoBuilder
from pathplannerlib.config import ModuleConfig, RobotConfig, PIDConstants
from pathplannerlib.controller import PPHolonomicDriveController
from wpilib import SmartDashboard
from wpilib import DriverStation
from wpimath.estimator import SwerveDrive4PoseEstimator
from wpimath.geometry import Pose2d, Rotation2d, Rotation3d, Translation2d
from wpimath.kinematics import ChassisSpeeds, SwerveDrive4Kinematics, SwerveModulePosition
from wpimath.system.plant import DCMotor


class SwerveDrivetrain(Subsystem):
    """
    Virtual representation of, and interface for, a full swerve drive
    """
    def __init__(self):
        """
        Creates a new swerve drivetrain.

        Returns:
            None: class initialization executed upon construction
        """
        self.constants = SwerveDriveConsts()
        self.invert_gyro = self.constants.invertGyro
        self.speedMultiplier = 1

        # must give in front-left, front-right, back-left, back-right order
        self.swerve_modules = [
            SwerveModuleMk4iSparkMaxNeoCanCoder(
                "frontLeft",
                (self.constants.moduleFrontLeftX, self.constants.moduleFrontLeftY),
                OperatorRobotConfig.swerve_module_channels[0],
                invert_drive=self.constants.moduleFrontLeftInvertDrive,
                invert_steer=self.constants.moduleFrontLeftInvertSteer,
                encoder_calibration=OperatorRobotConfig.swerve_abs_encoder_calibrations[0]
            ),
            SwerveModuleMk4iSparkMaxNeoCanCoder(
                "frontRight",
                (self.constants.moduleFrontRightX, self.constants.moduleFrontRightY),
                OperatorRobotConfig.swerve_module_channels[1],
                invert_drive=self.constants.moduleFrontRightInvertDrive,
                invert_steer=self.constants.moduleFrontRightInvertSteer,
                encoder_calibration=OperatorRobotConfig.swerve_abs_encoder_calibrations[1]
            ),
            SwerveModuleMk4iSparkMaxNeoCanCoder(
                "backLeft",
                (self.constants.moduleBackLeftX, self.constants.moduleBackLeftY),
                OperatorRobotConfig.swerve_module_channels[2],
                invert_drive=self.constants.moduleBackLeftInvertDrive,
                invert_steer=self.constants.moduleBackLeftInvertSteer,
                encoder_calibration=OperatorRobotConfig.swerve_abs_encoder_calibrations[2]
            ),
            SwerveModuleMk4iSparkMaxNeoCanCoder(
                "backRight",
                (self.constants.moduleBackRightX, self.constants.moduleBackRightY),
                OperatorRobotConfig.swerve_module_channels[3],
                invert_drive=self.constants.moduleBackRightInvertDrive,
                invert_steer=self.constants.moduleBackRightInvertSteer,
                encoder_calibration=OperatorRobotConfig.swerve_abs_encoder_calibrations[3]
            )
        ]

        self.drive_kinematics = SwerveDrive4Kinematics(
            *[swerve_module.drivetrain_location for swerve_module in self.swerve_modules] # -> Translation2d()
        )

        self.gyroscope = navx.AHRS.create_spi()
        self.heading_offset = Rotation3d()
        self.factory_default_gyro()

        self.pose_estimator = SwerveDrive4PoseEstimator(
            self.drive_kinematics,
            self.current_yaw(),
            self.current_module_positions(),
            self.get_default_starting_pose()
        )

        self.reset_heading()

        # Path Planner setup
        path_planner_config = RobotConfig.fromGUISettings()
        self.configure_path_planner(path_planner_config)

    def raw_current_heading(self) -> Rotation3d:
        """
        Get the gyroscope heading without adjusting by the starting heading offset. If the gyro
        needs to be inverted for CCW positive rotation, change the polarity of the heading

        Returns:
            The current 3D unadjusted heading from the gyroscope
        """
        return -self.gyroscope.getRotation3d() if self.invert_gyro else self.gyroscope.getRotation3d()

    def current_heading(self) -> Rotation3d:
        """
        Get the gyroscope heading adjusted by the starting heading offset - this ensures that a heading of
        zero corresponds to the front of the robot. CCW rotation will correspond to a positive increase in
        the Z component heading.

        Returns:
            The current 3D front-relative heading from the gyroscope
        """
        return self.raw_current_heading() - self.heading_offset

    def current_yaw(self) -> Rotation2d:
        """
        Get the current front-relative yaw of the robot, as determined by the offset-adjusted gyroscope reading.
        CCW rotation corresponds to a positive increase in the yaw.

        Returns:
            The current front-relative yaw of the robot
        """
        return Rotation2d(self.current_heading().Z())

    def factory_default_gyro(self) -> None:
        """
        Retrieve the starting reading from the gyroscope and save as the heading offset. This
        ensures that the front of the robot will correspond to 0 in the heading and yaw.

        Returns:
            None: object's heading offset updated in-place
        """
        self.heading_offset = self.gyroscope.getRotation3d()

    def reset_heading(self) -> None:
        """
        Reset the heading such that the robot's current gyroscope reading will correspond to 0 in any
        heading and yaw readings after this method is called. Odometry must also be reset with a rotation
        of 0 for it to continue to work properly.

        Returns:
            None: object's heading offset is updated in-place and pose estimator is reset
        """
        self.heading_offset = self.raw_current_heading()
        self.reset_pose_estimator(Pose2d(self.current_pose().translation(), Rotation2d()))

    def drive(
        self,
        velocity_vector_x: float,
        velocity_vector_y: float,
        angular_velocity: float,
        field_relative: bool = True,
    ) -> None:
        """
        Operate the swerve drive according to three given component velocities. These velocities
        will almost always come from human driver controller input. This method can be used for both
        robot-relative and field-relative drive.

        Args:
            velocity_vector_x: how fast, in meters per second, to translate in the X (+ front-to-back -) direction
            velocity_vector_y: how fast, in meters per second, to translate in the Y (+ left-to-right -) direction
            angular_velocity: how fast, in radians per second, to rotate the robot (CCW +)
            field_relative: if True, drive relative to the field (forward always means away from the driver station,
                left always means toward the left wall). If False, drive relative to the robot (forward means straight
                from the front side of the robot, left means straight from the left side of the robot).

        Returns:
            None: individual swerve modules are given new goal states to transition to in-place
        """
        dampener_use = self.speedMultiplier
        dampener_use_velocity_x, dampener_use_velocity_y, dampener_use_angular = (
            dampener_use, dampener_use, dampener_use
        )

        dampened_velocity_vector_x = dampener_use_velocity_x * velocity_vector_x
        dampened_velocity_vector_y = dampener_use_velocity_y * velocity_vector_y
        dampened_angular_velocity = dampener_use_angular * angular_velocity

        if field_relative:
            field_invert = 1
            if self.flip_to_red_alliance():
                field_invert = -1

            chassis_speeds = ChassisSpeeds.fromFieldRelativeSpeeds(
                field_invert * dampened_velocity_vector_x, field_invert * dampened_velocity_vector_y,
                dampened_angular_velocity, self.current_pose().rotation()
            )
        else:
            chassis_speeds = ChassisSpeeds(
                dampened_velocity_vector_x, dampened_velocity_vector_y, dampened_angular_velocity
            )

        self.set_states_from_speeds(chassis_speeds)

    def current_module_positions(self) -> Tuple[SwerveModulePosition]:
        """
        Get the current positions of each swerve module on the drivetrain. Position is defined as how far
        drive motors have driven so far, in meters, and the current absolute steer rotation of the wheel,
        in degrees with domain [0, 360).

        Returns:
            The current module positions, given in front-left, front-right, back-left, back-right order
        """
        return tuple([swerve_module.current_position() for swerve_module in self.swerve_modules])

    def current_pose(self) -> Pose2d:
        """
        Get the robot's current position on the field. We use the "always blue" field coordinate system,
        in which moving away from the blue driver station corresponds to increasing X values and moving
        toward the left field wall from the perspective of a blue driver corresponds to increasing Y values.
        A robot with the front side perfectly facing the red driver station has a rotation of zero. Rotation
        increases with CCW rotation of the robot.

        Returns:
            The robot's current position as a combination of field coordinate and field-relative rotation
        """
        return self.pose_estimator.getEstimatedPosition()

    def current_robot_relative_speed(self) -> ChassisSpeeds:
        """
        Get the translational and rotational velocities of the whole robot, with axial definitions relative to the robot (
        velocity in the robot's front and back directions correspond to + and - X velocity, velocity in
        the robot's left and right directions correspond to + and - Y velocity, velocity in CCW rotation
        when looking down on top of the robot corresponds to + angular velocity).

        Returns:
            The translational velocities, in meters per second, and rotational velocity, in radians per second
        """
        return self.drive_kinematics.toChassisSpeeds(tuple(
            swerve_module.current_state() for swerve_module in self.swerve_modules
        ))

    def set_states_from_speeds(self, drivetrain_speeds: ChassisSpeeds, apply_cosine_scaling: bool = True) -> None:
        """
        Directly set new goal states for each individual swerve module based on the given desired
        translational and rotational velocities for the whole drivetrain. This method is privately used
        as a link between driver inputs and the swerve modules. It is publicly used by specific motion
        commands (like autonomous routines).

        Args:
            drivetrain_speeds: the velocities we want the drivetrain to achieve
            apply_cosine_scaling: if True, scale the drive speed down according to how perpendicular
                the wheel is to the new state angle. If False, do not scale.

        Returns:
            None: new goal states are set for each swerve module in-place
        """
        module_states = self.drive_kinematics.toSwerveModuleStates(drivetrain_speeds)
        module_states = self.drive_kinematics.desaturateWheelSpeeds(module_states, self.constants.maxTranslationMPS)

        for i, module_state in enumerate(module_states):
            self.swerve_modules[i].set_state(module_state, apply_cosine_scaling=apply_cosine_scaling)

    def update_pose_estimator(self) -> None:
        """
        Update the pose estimator using the current module positions and the robot's current yaw.
        Additional contributors of pose estimation, like AprilTag readings, can be incorporated here.
        This method is expected to be called on each periodic clock tick.

        Returns:
            None: pose estimator is updated in-place
        """
        self.pose_estimator.update(self.current_yaw(), self.current_module_positions())

    def add_vision_pose_estimate(self, pose: Pose2d, timestamp: float, stdDevs: Tuple[float]) -> None:
        """
        Adds a vision-based pose estimate to the pose estimator. This method is expected to be called from the Vision class.

        Args:
            pose: the vision-based pose estimate

        Returns:
            None: pose estimator is updated in-place
        """
        self.pose_estimator.addVisionMeasurement(pose, timestamp, stdDevs)

    def reset_pose_estimator(self, current_pose: Pose2d) -> None:
        """
        Reset the robot's current pose to the given input. Should be called, at a minimum, before
        executing an autonomous routine.

        Args:
            current_pose: the robot's current field-relative position and rotation

        Returns:
            None: pose estimator is updated in-place
        """
        self.pose_estimator.resetPosition(self.current_yaw(), self.current_module_positions(), current_pose)
        self.stop_driving(apply_to_modules=False)

    def get_default_starting_pose(self) -> Pose2d:
        """
        Get the alliance-specific default starting pose for the drivetrain. This should be called
        in autonomous init if not using a routine that updates the starting odometry pose.
        If relying on this, the driver should quickly read an AprilTag using the camera once the match starts.

        Returns:
            default_starting_pose: the assumed starting pose given no other information
        """
        default_starting_pose = OperatorRobotConfig.blue_default_start_pose
        if self.flip_to_red_alliance():
            default_starting_pose = OperatorRobotConfig.red_default_start_pose

        default_starting_pose = Pose2d(
            Translation2d(*default_starting_pose[0:2]), Rotation2d.fromDegrees(default_starting_pose[2])
        )

        return default_starting_pose

    def stop_driving(self, apply_to_modules: bool = True) -> None:
        """
        Set all velocities to zero.

        Args:
            apply_to_modules: if True, change velocities on the modules to be zero. If False, do not.

        Returns:
            None: if desired, goal states are updated on the modules in-place
        """
        robot_relative_speeds = ChassisSpeeds.fromRobotRelativeSpeeds(ChassisSpeeds(0, 0, 0), self.current_yaw())
        module_states = self.drive_kinematics.toSwerveModuleStates(robot_relative_speeds)

        if apply_to_modules:
            for i, module_state in enumerate(module_states):
                self.swerve_modules[i].set_state(module_state)

    def set_motor_stop_modes(self, to_drive: bool, to_break: bool, all_motor_override: bool = False, burn_flash: bool = False) -> None:
        """
        Update the idle mode (coast vs break) for each swerve module. Coast means friction naturally
        determines when the motor comes to a stop, break means the motor comes to a stop as soon as possible.

        Args:
            to_drive: if True, change the idle mode of all drive motors. If False, cahnge the idle mode of all
                steer motors
            to_break: if True change the idle mode to break. If False, change the idle mode to coast
            all_motor_override: if True change all motors (drive and steer) to the desired idle mode. If False,
                only change the motors specified in to_drive.
            burn_flash: if True, save the idle mode changes to memory that persists across power cycles. If False,
                do not save in this manner (settings given here will disappear once the robot turns off)

        Returns:
            None: motor idle modes are updated in-place
        """
        for swerve_module in self.swerve_modules:
            swerve_module.set_motor_stop_mode(to_drive=to_drive, to_break=to_break)
            swerve_module.apply_motor_config(to_drive=to_drive, burn_flash=burn_flash)
            if all_motor_override:
                swerve_module.set_motor_stop_mode(to_drive=not to_drive, to_break=to_break)
                swerve_module.apply_motor_config(to_drive=not to_drive, burn_flash=burn_flash)

    def flip_to_red_alliance(self) -> bool:
        """
        Determine whether to flip autonomous routines and field-relative drive for the red alliance.
        Because alliance choice can change, this method should be called as part of code executed on
        periodic clock ticks.

        Returns:
            True if we should make flips for the red alliance, False otherwise
        """
        alliance = DriverStation.getAlliance()
        if alliance:
            return alliance == DriverStation.Alliance.kRed
        return False

    def gen_path_planner_config(self) -> RobotConfig:
        """
        Create a configuration object for PathPlanner based on the physical constants recorded
        for the overall drivetrain and the individual swerve modules. This should follow the
        same structure as the configuration generated using PathPlanner's GUI.

        THIS IS CURRENTLY BROKEN AND NEEDS TO BE DEBUGGED. DO NOT USE.

        Returns:
            PathPlanner configuration object based on our robot's properties
        """
        path_planner_config = RobotConfig(
            massKG=self.constants.massKG,
            MOI=self.constants.MOI,
            moduleConfig=ModuleConfig(
                wheelRadiusMeters=self.swerve_modules[0].constants.wheelDiameter / 2.0,
                maxDriveVelocityMPS=self.constants.maxTranslationMPS,
                wheelCOF=self.swerve_modules[0].constants.wheelCOF,
                driveMotor=getattr(DCMotor, self.swerve_modules[0].constants.motorType)(
                    self.swerve_modules[0].constants.numDriveMotors
                ),
                driveCurrentLimit=self.swerve_modules[0].constants.kDriveCurrentLimit,
                numMotors=self.swerve_modules[0].constants.numDriveMotors,
            ),
            moduleOffsets=[swerve_module.drivetrain_location for swerve_module in self.swerve_modules],
        )

        return path_planner_config

    def configure_path_planner(self, config: RobotConfig) -> None:
        """
        Set up PathPlanner to execute autonomous routines using this drivetrain.

        PathPlanner expects the following:

        - A method to retrieve the robot's current field-relative position and rotation.
            PathPlanner uses this to evaluate the difference between the expected progression
            along the path to the robot's actual position. The optimizer minimizes this error.
        - A method to reset the robot's current field-relative position and rotation.
            PathPlanner uses this to align the robot's virtual pose to the starting pose
            of the autonomous routine.
        - A method to retrieve the robot's current robot-relative velocities, translational and rotational.
            PathPlanner uses this to evaluate the difference between the expected velocities
            as the robot traverses the path and the robot's actual velocities. The optimizer minimizes this error.
        - A method to update each swerve module's goal state based on desired velocities for the overall drivetrain.
            PathPlanner uses this to command the robot to drive in accordance with its path.
        - A controller object that defines how actual robot velocities will be optimized against PathPlanner's
            desired velocities for the path. The object is configured with separate PID constants for
            translation and rotation.
        - A PathPlanner configuration object defining properties of the drivetrain and individual modules.
        - A method to determine whether autonomous routines should be flipped for the red alliance.
        - A subsystem to require for PathPlanner's commands.

        Args:
            config: PathPlanner configuration object defining properties of the drivetrain and individual modules

        Returns:
            None: PathPlanner's AutoBuilder is configured in-place
        """
        AutoBuilder.configure(
            self.current_pose,
            self.reset_pose_estimator,
            self.current_robot_relative_speed,
            lambda speeds, feedforwards: self.set_states_from_speeds(speeds, apply_cosine_scaling=False),
            PPHolonomicDriveController(
                PIDConstants(*OperatorRobotConfig.pathplanner_translation_pid),
                PIDConstants(*OperatorRobotConfig.pathplanner_rotation_pid)
            ),
            config,
            self.flip_to_red_alliance,
            self
        )

    def setSpeedMultiplier(self, speedMult):
        """
        Set the multiplier for the drivetrain (between 0 and 1).
        """
        self.speedMultiplier = speedMult

    def periodic(self) -> None:
        """
        Execute code on every periodic clock tick, regardless of the robot's game mode state
        (disabled, autonomous, teleoperated, test).
        """
        self.update_pose_estimator()
        # TODO: delete prints
        SmartDashboard.putNumber("top left drive", self.swerve_modules[0].drive_motor_encoder.getVelocity())
        SmartDashboard.putNumber("top right drive", self.swerve_modules[1].drive_motor_encoder.getVelocity())
        SmartDashboard.putNumber("bottom left drive", self.swerve_modules[2].drive_motor_encoder.getVelocity())
        SmartDashboard.putNumber("bottom right drive", self.swerve_modules[3].drive_motor_encoder.getVelocity())
