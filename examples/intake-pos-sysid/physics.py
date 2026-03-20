import math

import rev
import wpilib
import wpilib.simulation
from pyfrc.physics.core import PhysicsInterface
from wpimath.system.plant import DCMotor

# -------------------------------------------------------------------------
# Arm geometry / inertia (update these to match the real mechanism)
# -------------------------------------------------------------------------
kGearRatio = 10.0        # 10:1 reduction
kArmMassKg = 0.9         # ~2 lbs — update with actual mass
kArmLengthM = 0.3        # ~12 inches — update with actual length
# Moment of inertia for a thin rod rotating about one end: (1/3) * m * L^2
kArmMOI = (1.0 / 3.0) * kArmMassKg * kArmLengthM ** 2

# -------------------------------------------------------------------------
# Angle convention
# -------------------------------------------------------------------------
# Our system:   0° = straight down (vertical), +° = deployed direction
# WPILib sim:   0° = horizontal,               +° = counterclockwise
#
# The arm's natural resting position (gravity equilibrium) is at our -15°.
# SingleJointedArmSim pulls toward its own "straight down" (-90° in sim).
# To make sim's "straight down" = our -15°, we shift the offset by +15°:
#   sim_angle = our_angle - 90° + 15° = our_angle - 75°
# Verification:
#   our -15° → sim: -15° - 75° = -90° (straight down, gravity equilibrium) ✓
#   our   0° → sim:   0° - 75° = -75° (gravity still pulls toward -15°)     ✓
#   our  90° → sim:  90° - 75° =  15° (deployed, gravity pulls it back)      ✓
# -------------------------------------------------------------------------
kOurStartAngleDeg = -4.0    # arm starts slightly past vertical (stowed side)
kOurMinAngleDeg = -15.0     # reverse hard stop (stowed, gravity equilibrium)
kOurMaxAngleDeg = 120.0     # forward hard stop (deployed)

_GRAVITY_OFFSET_DEG = 90.0 - abs(kOurMinAngleDeg)  # = 75.0


def _to_sim_rad(our_deg: float) -> float:
    """Convert our angle (0=down, gravity eq at -15°) to WPILib sim radians."""
    return math.radians(our_deg - _GRAVITY_OFFSET_DEG)


def _to_our_deg(sim_rad: float) -> float:
    """Convert WPILib sim radians to our degrees (0=down, gravity eq at -15°)."""
    return math.degrees(sim_rad) + _GRAVITY_OFFSET_DEG


class PhysicsEngine:
    """
    Simulates intake arm physics.

    The arm starts at -4° and falls to -15° (the natural gravity equilibrium
    and reverse hard stop).  Without motor input it rests there.

    Angle conventions:
      - Robot code / encoder: 0° = straight down, negative = stowed side
      - SingleJointedArmSim:  0° = horizontal; gravity equilibrium at -90°
      - Offset of -75° maps our -15° onto the sim's -90° (equilibrium)
    """

    def __init__(self, physics_controller: PhysicsInterface, robot) -> None:
        self.physics_controller = physics_controller

        # Physics simulation for the arm
        self.arm_sim = wpilib.simulation.SingleJointedArmSim(
            DCMotor.NEO(1),
            kGearRatio,
            kArmMOI,
            kArmLengthM,
            _to_sim_rad(kOurMinAngleDeg),   # min: our -15° → sim -105°
            _to_sim_rad(kOurMaxAngleDeg),   # max: our 120° → sim  30°
            True,                            # simulate gravity
            _to_sim_rad(kOurStartAngleDeg), # start: our -4° → sim -94°
        )

        # SparkMax sim device — gives us applied output and encoder feedback
        self.motor_sim = rev.SparkMaxSim(robot.intake.motor, DCMotor.NEO(1))
        self.enc_sim = self.motor_sim.getRelativeEncoderSim()

        # Seed the encoder at the starting position so the arm doesn't
        # snap to zero on the first cycle
        self.enc_sim.setPosition(_to_our_deg(_to_sim_rad(kOurStartAngleDeg)))

        # Debug telemetry — visible in SmartDashboard under /PhysicsSim/
        self._nt_applied_v = wpilib.SmartDashboard.getEntry("PhysicsSim/appliedVoltage")
        self._nt_arm_angle = wpilib.SmartDashboard.getEntry("PhysicsSim/armAngleDeg")

    def update_sim(self, now: float, tm_diff: float) -> None:
        # Read what the robot code commanded.
        # getAppliedOutput() does not reflect setVoltage() calls in simulation —
        # getSetpoint() returns the raw value passed to setVoltage(v) (volts)
        # or set(pct) (duty-cycle fraction).  Since this subsystem exclusively
        # uses setVoltage(), getSetpoint() returns volts directly.
        applied_voltage = self.motor_sim.getSetpoint()

        # Step the physics simulation
        self.arm_sim.setInputVoltage(applied_voltage)
        self.arm_sim.update(tm_diff)

        # Push velocity and position back to the encoder sim.
        # setVelocity() updates encoder.getVelocity() so calibration stall
        # detection works correctly.  iterate() integrates from the current
        # encoder position (rather than overwriting it), so calibration's
        # encoder.setPosition(0) zero-setting is preserved between cycles.
        arm_velocity_deg_s = math.degrees(self.arm_sim.getVelocity())
        self.enc_sim.setVelocity(arm_velocity_deg_s)
        self.enc_sim.iterate(arm_velocity_deg_s, tm_diff)
        self.motor_sim.setMotorCurrent(self.arm_sim.getCurrentDraw())

        self._nt_applied_v.setDouble(applied_voltage)
        self._nt_arm_angle.setDouble(math.degrees(self.arm_sim.getAngle()))
