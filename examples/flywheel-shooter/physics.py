import typing

import rev
from pyfrc.physics.core import PhysicsInterface
from pyfrc.physics import motor_cfgs, tankmodel
from pyfrc.physics.units import units
from wpimath.geometry import Pose2d, Rotation2d
from wpimath.system.plant import DCMotor

if typing.TYPE_CHECKING:
    from robot import MyRobot


class PhysicsEngine:
    def __init__(self, physics_controller: PhysicsInterface, robot: "MyRobot"):
        self.physics_controller = physics_controller

        # Set initial robot pose and field objects
        self.physics_controller.field.setRobotPose(Pose2d(1, 1, Rotation2d.fromDegrees(90)))
        self.physics_controller.field.getObject("Blue Goal").setPose(Pose2d(4.6, 4, Rotation2d()))

        self.l_motor = rev.SparkSim(robot.drivetrain.left_motor, DCMotor.NEO())
        self.r_motor = rev.SparkSim(robot.drivetrain.right_motor, DCMotor.NEO())

        # Configure drivetrain model so speed=1.0 produces ~1 m/s
        # Using NEO motor config with a gear ratio and wheel size chosen
        # to give approximately 1 m/s at full speed.
        self.drivetrain = tankmodel.TankModel.theory(
            motor_cfgs.MOTOR_CFG_NEO_550,
            50 * units.lbs,
            1.0,                                # gear ratio
            1,                                  # motors per side
            22 * units.inch,                    # wheelbase
            26 * units.inch,                    # robot width
            32 * units.inch,                    # robot length
            6 * units.inch,                     # wheel diameter
        )

    def update_sim(self, now: float, tm_diff: float) -> None:
        # Read motor output via SparkSim
        self.l_motor.setAppliedOutput(self.l_motor.getSetpoint() * 12)
        self.r_motor.setAppliedOutput(self.r_motor.getSetpoint() * 12)
        l_spark = self.l_motor.getAppliedOutput()
        r_spark = self.r_motor.getAppliedOutput()
        # Read motor output via .get() on the actual motor
        #print(dir(self.l_motor))
        l_get = self.l_motor.getAppliedOutput()
        r_get = self.r_motor.getAppliedOutput()
        # Read motor output via SimDeviceSim
        #l_sim = self.l_sim_output.get()
        #r_sim = self.r_sim_output.get()
        l_sim = 0
        r_sim = 0
        #if abs(l_get) > 0.01 or abs(r_get) > 0.01 or abs(l_spark) > 0.01 or abs(l_sim) > 0.01 or True:
        #    print(f"DEBUG: SparkSim l={l_spark:.3f} r={r_spark:.3f} | .get() l={l_get:.3f} r={r_get:.3f} | SimDevice l={l_sim:.3f} r={r_sim:.3f}")

        transform = self.drivetrain.calculate(l_spark, r_spark, tm_diff)
        self.physics_controller.move_robot(transform)
