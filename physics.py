"""
Swerve drive physics simulation for pyfrc.

Applies a zero-delay plant model: each cycle, the drive encoder velocity
and steer encoder position are set directly from the module's last commanded
state.  This makes closed-loop PID control, odometry, and Mechanism2d
visualization all respond correctly in simulation without tuning a dynamic model.

Robot field pose is integrated from swerve kinematics and fed back to:
  - The Field2d widget (visible in the sim GUI)
  - The NavX gyro sim device (so heading-based field-relative drive works)

On macOS the WPILib sim GUI (GLFW) cannot read Xbox/PlayStation controller
inputs because Apple's Game Controller framework intercepts them.  An optional
SDL2-based bridge detects this at runtime — when a joystick port is mapped in
the sim GUI but reports 0 axes, the bridge takes over and feeds controller
data into the HAL sim.  Install ``pysdl2`` and ``pysdl2-dll`` to enable
(not needed on Windows/Linux).
"""

import logging
import sys
import threading
import time
import typing

import hal.simulation
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

logger = logging.getLogger("physics")


# ---------------------------------------------------------------------------
# macOS SDL2 controller bridge
# ---------------------------------------------------------------------------

def _start_sdl2_controller_bridge(port: int) -> None:
    """Spawn a daemon thread that reads one game controller via SDL2 and
    feeds its state into ``GenericHIDSim`` for the given WPILib joystick
    *port*.

    Called only when macOS is detected and the port has a mapped controller
    with 0 reported axes (GLFW bug).
    """
    try:
        import sdl2
    except ImportError:
        logger.warning(
            "pysdl2 not installed — Xbox controller input in sim requires "
            "'pip install pysdl2 pysdl2-dll' on macOS"
        )
        return

    # --- mapping tables: SDL2 game controller → WPILib XboxController ---
    _AXIS_MAP = {
        sdl2.SDL_CONTROLLER_AXIS_LEFTX: 0,
        sdl2.SDL_CONTROLLER_AXIS_LEFTY: 1,
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT: 2,
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT: 3,
        sdl2.SDL_CONTROLLER_AXIS_RIGHTX: 4,
        sdl2.SDL_CONTROLLER_AXIS_RIGHTY: 5,
    }
    _BUTTON_MAP = {
        sdl2.SDL_CONTROLLER_BUTTON_A: 1,
        sdl2.SDL_CONTROLLER_BUTTON_B: 2,
        sdl2.SDL_CONTROLLER_BUTTON_X: 3,
        sdl2.SDL_CONTROLLER_BUTTON_Y: 4,
        sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: 5,
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: 6,
        sdl2.SDL_CONTROLLER_BUTTON_BACK: 7,
        sdl2.SDL_CONTROLLER_BUTTON_START: 8,
        sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK: 9,
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK: 10,
    }
    _DPAD = [
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP,
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN,
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT,
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
    ]

    def _dpad_to_pov(up, down, left, right):
        if up and right:
            return 45
        if right and down:
            return 135
        if down and left:
            return 225
        if left and up:
            return 315
        if up:
            return 0
        if right:
            return 90
        if down:
            return 180
        if left:
            return 270
        return -1

    def _bridge_thread():
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_MFI, b"1")
        sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER)

        # Allow time for controller discovery
        for _ in range(20):
            sdl2.SDL_PumpEvents()
            time.sleep(0.05)

        # Find the first game-controller-capable device
        gc = None
        for idx in range(sdl2.SDL_NumJoysticks()):
            if sdl2.SDL_IsGameController(idx):
                gc = sdl2.SDL_GameControllerOpen(idx)
                break

        if not gc:
            logger.info("SDL2 bridge: no game controllers found")
            sdl2.SDL_Quit()
            return

        gc_name = sdl2.SDL_GameControllerName(gc)
        if gc_name and isinstance(gc_name, bytes):
            gc_name = gc_name.decode()
        logger.warning("SDL2 bridge: '%s' → HAL joystick port %d", gc_name, port)

        sim = wpilib.simulation.GenericHIDSim(port)
        sim.setAxisCount(6)
        sim.setButtonCount(10)
        sim.setPOVCount(1)

        while True:
            sdl2.SDL_PumpEvents()

            for sdl_axis, wpi_axis in _AXIS_MAP.items():
                raw = sdl2.SDL_GameControllerGetAxis(gc, sdl_axis)
                sim.setRawAxis(wpi_axis, raw / 32767.0)

            for sdl_btn, wpi_btn in _BUTTON_MAP.items():
                sim.setRawButton(
                    wpi_btn,
                    bool(sdl2.SDL_GameControllerGetButton(gc, sdl_btn)),
                )

            dpad = [
                bool(sdl2.SDL_GameControllerGetButton(gc, b)) for b in _DPAD
            ]
            sim.setPOV(0, _dpad_to_pov(*dpad))

            time.sleep(0.01)

    t = threading.Thread(
        target=_bridge_thread, daemon=True, name="sdl2-controller-bridge"
    )
    t.start()


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
        self._has_shooter = shooter is not None
        if self._has_shooter:
            self._shooter_lead_sim = rev.SparkSim(shooter.leadMotor, DCMotor.neoVortex())
            self._shooter_follower_sim = rev.SparkSim(shooter.followerMotor, DCMotor.neoVortex())
            # Two NEO Vortex motors, ~0.005 kg·m² moment of inertia (dual 4" wheels), 1:1 gearing
            self._flywheel_sim = wpilib.simulation.FlywheelSim(
                LinearSystemId.flywheelSystem(DCMotor.neoVortex(2), 0.005, 1.0),
                DCMotor.neoVortex(2),
            )

        # Vision simulation — safe to skip if localization is disabled
        self._localization = getattr(robot.container, 'localization', None)
        if self._localization is not None:
            self._localization.setup_sim()

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

        # macOS controller bridge state — checked each tick until resolved.
        # We monitor joystick ports 0 and 1 (driver and operator).  Once a
        # port is assigned in the sim GUI but reports 0 axes we know GLFW
        # cannot read it and start the SDL2 bridge for that port.
        if sys.platform == "darwin":
            self._controller_bridge_ports_to_check: set[int] = {0, 1}
        else:
            self._controller_bridge_ports_to_check: set[int] = set()

    def _check_controller_bridge(self) -> None:
        """On macOS, detect joystick ports that are mapped but broken (0 axes)
        and start the SDL2 bridge for them.  Removes ports from the check set
        once resolved (either working or bridged)."""
        resolved = set()
        for port in self._controller_bridge_ports_to_check:
            axis_count, button_count, _ = hal.simulation.getJoystickCounts(port)
            if axis_count > 0:
                # GLFW is reading this port fine — no bridge needed
                resolved.add(port)
            elif button_count > 0:
                # Controller is mapped (has buttons) but reports 0 axes —
                # this is the broken GLFW state on macOS.
                logger.warning(
                    "macOS GLFW reports 0 axes for joystick port %d "
                    "(buttons=%d) — starting SDL2 bridge",
                    port, button_count,
                )
                _start_sdl2_controller_bridge(port)
                resolved.add(port)
            # else: nothing mapped yet, keep checking
        self._controller_bridge_ports_to_check -= resolved

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
        # Check for broken macOS controller input each tick until resolved.
        if self._controller_bridge_ports_to_check:
            self._check_controller_bridge()

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
        if len(module_states) != 4:
            return
        speeds = self.kinematics.toChassisSpeeds(tuple(module_states))
        self._pose = self._pose.exp(
            Twist2d(
                speeds.vx * tm_diff,
                speeds.vy * tm_diff,
                speeds.omega * tm_diff,
            )
        )

        # Feed ground-truth pose to vision sim so cameras see AprilTags
        if self._localization is not None:
            self._localization.update_sim(self._pose)

        # Update Field2d widget and struct publisher with the integrated pose.
        self.physics_controller.field.setRobotPose(self._pose)
        self._gt_pose_pub.set(self._pose)

        # Feed integrated heading back to the NavX gyro sim device so that
        # field-relative drive and pose estimation use the correct heading.
        if self._navx_yaw is not None:
            self._navx_yaw.set(self._pose.rotation().degrees())

        # Simulate shooter flywheel (if enabled)
        if self._has_shooter:
            flywheel_rpm = self._flywheel_sim.getAngularVelocity() * 60.0 / (2 * 3.14159)
            self._shooter_lead_sim.iterate(flywheel_rpm, 12.0, tm_diff)
            lead_output = self._shooter_lead_sim.getAppliedOutput()
            self._flywheel_sim.setInputVoltage(lead_output * 12.0)
            self._flywheel_sim.update(tm_diff)
            flywheel_rpm = self._flywheel_sim.getAngularVelocity() * 60.0 / (2 * 3.14159)
            lead_enc = self._shooter_lead_sim.getRelativeEncoderSim()
            lead_enc.setVelocity(flywheel_rpm)
            lead_enc.setPosition(lead_enc.getPosition() + flywheel_rpm / 60.0 * tm_diff)
            follower_enc = self._shooter_follower_sim.getRelativeEncoderSim()
            follower_enc.setVelocity(flywheel_rpm)
            follower_enc.setPosition(lead_enc.getPosition())

