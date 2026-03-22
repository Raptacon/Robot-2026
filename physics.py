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
import rev
import wpilib
import wpilib.simulation
from pyfrc.physics.core import PhysicsInterface
from wpimath.geometry import Rotation2d, Twist2d
from wpimath.kinematics import SwerveModuleState
from wpimath.system.plant import DCMotor

if typing.TYPE_CHECKING:
    from robot import MyRobot

logger = logging.getLogger("physics")


# ---------------------------------------------------------------------------
# macOS SDL2 controller bridge
# ---------------------------------------------------------------------------

def _start_sdl2_controller_bridge() -> None:
    """Spawn a daemon thread that discovers game controllers via SDL2 and
    feeds their state into the HAL sim.

    The first controller found maps to WPILib joystick port 0 (driver),
    the second to port 1 (operator).  If no controllers are detected the
    thread exits silently and the sim GUI's virtual joystick still works.
    """
    try:
        import sdl2
    except ImportError:
        msg = (
            "pysdl2 not installed — Xbox controller input in sim requires "
            "'pip install pysdl2 pysdl2-dll' on macOS"
        )
        wpilib.reportWarning(msg)
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
    # SDL2 button → bit index for HAL button bitmask.
    # WPILib buttons are 1-based; bit 0 = button 1 (A), bit 1 = button 2 (B), etc.
    _BUTTON_MAP = {
        sdl2.SDL_CONTROLLER_BUTTON_A: 0,
        sdl2.SDL_CONTROLLER_BUTTON_B: 1,
        sdl2.SDL_CONTROLLER_BUTTON_X: 2,
        sdl2.SDL_CONTROLLER_BUTTON_Y: 3,
        sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: 4,
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: 5,
        sdl2.SDL_CONTROLLER_BUTTON_BACK: 6,
        sdl2.SDL_CONTROLLER_BUTTON_START: 7,
        sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK: 8,
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK: 9,
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

        # Open all game-controller-capable devices, map to WPILib ports.
        # First controller → port 0 (driver), second → port 1 (operator).
        controllers = []  # list of (sdl2_gc, port)
        for idx in range(sdl2.SDL_NumJoysticks()):
            if not sdl2.SDL_IsGameController(idx):
                continue
            gc = sdl2.SDL_GameControllerOpen(idx)
            if not gc:
                continue
            port = len(controllers)
            gc_name = sdl2.SDL_GameControllerName(gc)
            if gc_name and isinstance(gc_name, bytes):
                gc_name = gc_name.decode()
            wpilib.reportWarning(
                f"SDL2 bridge: '{gc_name}' → HAL joystick port {port}. "
                f"Do NOT assign this controller in the sim GUI System Joystick panel."
            )
            hal.simulation.setJoystickAxisCount(port, 6)
            hal.simulation.setJoystickButtonCount(port, 10)
            hal.simulation.setJoystickPOVCount(port, 1)
            hal.simulation.setJoystickIsXbox(port, True)
            hal.simulation.setJoystickName(port, gc_name or "SDL2 Controller")
            controllers.append((gc, port))

        if not controllers:
            # No physical controllers — exit silently so the sim GUI's
            # virtual joystick panel still works.
            sdl2.SDL_Quit()
            return

        # Poll loop — ~100 Hz to keep input responsive
        while True:
            sdl2.SDL_PumpEvents()

            for gc, port in controllers:
                for sdl_axis, wpi_axis in _AXIS_MAP.items():
                    raw = sdl2.SDL_GameControllerGetAxis(gc, sdl_axis)
                    hal.simulation.setJoystickAxis(port, wpi_axis, raw / 32767.0)

                buttons = 0
                for sdl_btn, bit_index in _BUTTON_MAP.items():
                    if sdl2.SDL_GameControllerGetButton(gc, sdl_btn):
                        buttons |= (1 << bit_index)
                hal.simulation.setJoystickButtonsValue(port, buttons)

                dpad = [
                    bool(sdl2.SDL_GameControllerGetButton(gc, b))
                    for b in _DPAD
                ]
                hal.simulation.setJoystickPOV(port, 0, _dpad_to_pov(*dpad))

            hal.simulation.notifyDriverStationNewData()
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
        self.modules = modules
        self.drive_sims = [
            rev.SparkSim(m.drive_motor, DCMotor.NEO()) for m in modules
        ]
        self.steer_sims = [
            rev.SparkSim(m.steer_motor, DCMotor.NEO()) for m in modules
        ]
        self.kinematics = robot.container.drivetrain.drive_kinematics

        # Seed all encoders to 0° (wheels forward) immediately.
        #
        # baseline_relative_encoders() runs during module __init__ and sets each
        # steer relative encoder to the module's calibration angle (e.g. 241° for
        # FL).  The robot periodic runs before the first update_sim(), so if these
        # stale values are left in place, optimize() sees a large angle error on the
        # first set_state() call and begins oscillating.  Seeding here ensures the
        # first robot periodic sees a clean 0° reading on every module.
        for module, drive_sim, steer_sim in zip(self.modules, self.drive_sims, self.steer_sims):
            calibration = module.constants.encoder_calibration

            steer_enc = steer_sim.getRelativeEncoderSim()
            steer_enc.setPosition(0.0)
            steer_enc.setVelocity(0.0)

            # Set CANcoder raw = -calibration so absolute position reads 0.0 (forward).
            # current_raw_absolute_steer_position() uses is-not-None, so 0.0 is
            # accepted and returns 0°, consistent with the relative encoder above.
            module.absolute_encoder.sim_state.set_supply_voltage(12.0)
            module.absolute_encoder.sim_state.set_raw_position(-calibration)

            drive_enc = drive_sim.getRelativeEncoderSim()
            drive_enc.setPosition(0.0)
            drive_enc.setVelocity(0.0)

        # Seed pose from the drivetrain's configured default starting position.
        self._pose = robot.container.drivetrain.get_default_starting_pose()

        # NavX yaw variable — may be unavailable depending on sim state.
        self._navx_yaw = None
        try:
            navx_sim = wpilib.simulation.SimDeviceSim("navX-Sensor[4]")
            self._navx_yaw = navx_sim.getDouble("Yaw")
        except Exception:
            # NavX sim device or Yaw entry may be unavailable in some sim setups;
            # ignore errors here and leave _navx_yaw as None.
            pass

        # On macOS, GLFW cannot read Xbox/PlayStation controllers at all
        # (reports 0 axes, 0 buttons).  Start the SDL2 bridge immediately
        # for the driver controller port.
        if sys.platform == "darwin":
            _start_sdl2_controller_bridge()

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
            velocity = module._last_commanded_state.speed          # m/s (signed)
            angle_deg = module._last_commanded_state.angle.degrees()  # degrees

            # Normalize steer to [0°, 180°) so that the two equivalent wheel
            # orientations — {+v, 180°} and {-v, 0°} — always write the same
            # encoder value.  Without this, optimize() sees 0° one cycle and
            # 180° the next, flip-flopping the commanded angle and oscillating
            # the steer motor every cycle at the 0°/180° boundary.
            steer_angle = angle_deg % 360.0
            if steer_angle >= 180.0:
                steer_angle -= 180.0

            # Drive — set encoder velocity and integrate position.
            # Uses the original velocity so drive odometry stays correct.
            drive_enc = drive_sim.getRelativeEncoderSim()
            drive_enc.setVelocity(velocity)
            drive_enc.setPosition(drive_enc.getPosition() + velocity * tm_diff)

            # Steer — set relative encoder to the normalized angle.
            steer_enc = steer_sim.getRelativeEncoderSim()
            steer_enc.setPosition(steer_angle)

            # Update CANcoder with the normalized angle.
            #   absolute_position = raw_position + calibration
            #   raw_position = steer_angle/360 - calibration
            calibration = module.constants.encoder_calibration
            module.absolute_encoder.sim_state.set_supply_voltage(12.0)
            module.absolute_encoder.sim_state.set_raw_position(
                steer_angle / 360.0 - calibration
            )

            # Kinematics uses the original angle so chassis-speed integration
            # (pose and NavX feedback) remains physically correct.
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

        # Update Field2d widget with the integrated pose.
        self.physics_controller.field.setRobotPose(self._pose)

        # Feed integrated heading back to the NavX gyro sim device so that
        # field-relative drive and pose estimation use the correct heading.
        if self._navx_yaw is not None:
            self._navx_yaw.set(self._pose.rotation().degrees())
