"""
Swerve drive physics simulation for pyfrc.

Applies a zero-delay plant model: each cycle, the drive encoder velocity
and steer encoder position are set directly from the module's last commanded
state.  This makes closed-loop PID control, odometry, and Mechanism2d
visualization all respond correctly in simulation without tuning a dynamic model.

Robot field pose is integrated from swerve kinematics and fed back to:
  - The Field2d widget (visible in the sim GUI)
  - The NavX gyro sim device (so heading-based field-relative drive works)
"""

import typing

import ntcore
import rev
import wpilib
import wpilib.simulation
from pyfrc.physics.core import PhysicsInterface
from wpimath.system.plant import LinearSystemId
from wpimath.geometry import Pose2d, Rotation2d, Twist2d
from wpimath.kinematics import SwerveModuleState
from wpimath.system.plant import DCMotor

if typing.TYPE_CHECKING:
    from robot import MyRobot


class PhysicsEngine:
    """
    No-delay swerve drive physics model.

    Drive encoder velocity and steer encoder position are written from
    _last_commanded_state each cycle, giving an instantaneous plant
    response suitable for basic simulation and visualization.

    All encoders are seeded to 0 degrees (wheels forward) in __init__ to
    prevent the calibration-based baseline from interfering with optimize()
    before the first physics tick runs.
    """

    def __init__(self, physics_controller: PhysicsInterface, robot: "MyRobot") -> None:
        self.physics_controller = physics_controller

        modules = robot.container.drivetrain.swerve_modules
        if len(modules) != 4:
            raise RuntimeError(
                f"PhysicsEngine requires exactly 4 swerve modules, got {len(modules)}. "
                "CANcoder initialization likely failed — check CAN IDs and phoenix6 sim setup."
            )
        self.modules = modules
        self.drive_sims = [
            rev.SparkSim(m.drive_motor, DCMotor.NEO()) for m in modules
        ]
        self.steer_sims = [
            rev.SparkSim(m.steer_motor, DCMotor.NEO()) for m in modules
        ]
        self.kinematics = robot.container.drivetrain.drive_kinematics

        # Seed all encoders to 0° (wheels forward) immediately.
        for module, drive_sim, steer_sim in zip(self.modules, self.drive_sims, self.steer_sims):
            calibration = module.constants.encoder_calibration

            steer_enc = steer_sim.getRelativeEncoderSim()
            steer_enc.setPosition(0.0)
            steer_enc.setVelocity(0.0)

            module.absolute_encoder.sim_state.set_supply_voltage(12.0)
            module.absolute_encoder.sim_state.set_raw_position(-calibration)

            drive_enc = drive_sim.getRelativeEncoderSim()
            drive_enc.setPosition(0.0)
            drive_enc.setVelocity(0.0)

        # Shooter flywheel simulation using WPILib FlywheelSim
        shooter = robot.container.shooter
        self._shooter_lead_sim = rev.SparkSim(shooter.leadMotor, DCMotor.neoVortex())
        self._shooter_follower_sim = rev.SparkSim(shooter.followerMotor, DCMotor.neoVortex())
        # Two NEO Vortex motors, ~0.005 kg·m² moment of inertia (dual 4" wheels), 1:1 gearing
        self._flywheel_sim = wpilib.simulation.FlywheelSim(
            LinearSystemId.flywheelSystem(DCMotor.neoVortex(2), 0.005, 1.0),
            DCMotor.neoVortex(2),
        )

        # Seed pose from the drivetrain's configured default starting position.
        self._pose = robot.container.drivetrain.get_default_starting_pose()

        # Ground-truth pose struct publisher (for AdvantageScope ghost overlay)
        self._gt_pose_pub = ntcore.NetworkTableInstance.getDefault().getStructTopic(
            "SimGroundTruth/pose", Pose2d
        ).publish()

        # NavX yaw variable — may be unavailable depending on sim state.
        self._navx_yaw = None
        try:
            navx_sim = wpilib.simulation.SimDeviceSim("navX-Sensor[4]")
            self._navx_yaw = navx_sim.getDouble("Yaw")
        except Exception:
            # NavX sim device or Yaw entry may be unavailable in some sim setups;
            # ignore errors here and leave _navx_yaw as None.
            pass

    def update_sim(self, now: float, tm_diff: float) -> None:
        """
        Called every simulation tick.

        Reads _last_commanded_state from each module and writes those values
        directly to the encoder sims (no-delay model), then integrates robot
        pose from swerve kinematics.

        Using _last_commanded_state instead of SparkSim.getSetpoint() avoids
        any uncertainty about whether the SparkSim API returns converted units
        (degrees / m/s) or raw encoder units.

        Args:
            now: current timestamp in seconds
            tm_diff: elapsed time since last call in seconds
        """
        module_states = []

        for module, drive_sim, steer_sim in zip(
            self.modules, self.drive_sims, self.steer_sims
        ):
            velocity = module._last_commanded_state.speed
            angle_deg = module._last_commanded_state.angle.degrees()

            steer_angle = angle_deg % 360.0
            if steer_angle >= 180.0:
                steer_angle -= 180.0

            drive_enc = drive_sim.getRelativeEncoderSim()
            drive_enc.setVelocity(velocity)
            drive_enc.setPosition(drive_enc.getPosition() + velocity * tm_diff)

            steer_enc = steer_sim.getRelativeEncoderSim()
            steer_enc.setPosition(steer_angle)

            calibration = module.constants.encoder_calibration
            module.absolute_encoder.sim_state.set_supply_voltage(12.0)
            module.absolute_encoder.sim_state.set_raw_position(
                steer_angle / 360.0 - calibration
            )

            module_states.append(
                SwerveModuleState(velocity, Rotation2d.fromDegrees(angle_deg))
            )

        # Integrate chassis speeds into robot pose.
        speeds = self.kinematics.toChassisSpeeds(tuple(module_states))
        self._pose = self._pose.exp(
            Twist2d(
                speeds.vx * tm_diff,
                speeds.vy * tm_diff,
                speeds.omega * tm_diff,
            )
        )

        # Update Field2d widget and struct publisher with the integrated pose.
        self.physics_controller.field.setRobotPose(self._pose)
        self._gt_pose_pub.set(self._pose)

        # Feed integrated heading back to the NavX gyro sim device so that
        # field-relative drive and pose estimation use the correct heading.
        if self._navx_yaw is not None:
            self._navx_yaw.set(self._pose.rotation().degrees())

        # Simulate shooter flywheel with proper inertia model
        lead_output = self._shooter_lead_sim.getAppliedOutput()
        self._flywheel_sim.setInputVoltage(lead_output * 12.0)
        self._flywheel_sim.update(tm_diff)
        # FlywheelSim outputs rad/s, convert to RPM for the encoder
        flywheel_rpm = self._flywheel_sim.getAngularVelocity() * 60.0 / (2 * 3.14159)
        # Update both motor encoders
        lead_enc = self._shooter_lead_sim.getRelativeEncoderSim()
        lead_enc.setVelocity(flywheel_rpm)
        lead_enc.setPosition(lead_enc.getPosition() + flywheel_rpm / 60.0 * tm_diff)
        follower_enc = self._shooter_follower_sim.getRelativeEncoderSim()
        follower_enc.setVelocity(flywheel_rpm)
        follower_enc.setPosition(lead_enc.getPosition())

