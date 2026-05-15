"""
SDL2 controller bridge for macOS WPILib simulation.

Problem
-------
The WPILib sim GUI uses GLFW for joystick input.  On macOS, Apple's Game
Controller framework claims Xbox and PlayStation controllers at the OS level,
preventing GLFW from reading their axes or buttons (it reports 0 for both).
This makes physical controllers unusable in the simulator on Mac.

Solution
--------
SDL2 has native support for macOS's Game Controller framework and can read
these controllers correctly.  This module spawns a daemon thread that:

1. Initializes SDL2 and discovers connected game controllers.
2. Maps each controller to a WPILib joystick port (first → port 0, second → port 1).
3. Polls controller state at ~100 Hz and writes it to the HAL sim via
   ``hal.simulation`` functions.

The bridge writes directly to the HAL joystick data, bypassing the sim GUI's
GLFW-based joystick handling entirely.

Important
---------
**Do NOT assign the controller in the sim GUI's System Joystick panel.**
If a controller is assigned there, the sim GUI will overwrite the HAL data
with GLFW's empty values each tick, cancelling out the bridge's writes.

If no physical controllers are detected, the bridge exits silently and the
sim GUI's virtual joystick (keyboard-driven) panel continues to work normally.

Requirements
------------
macOS only.  Install with::

    pip install pysdl2 pysdl2-dll

These are listed in ``requirements.txt`` with ``sys_platform == "darwin"``
markers so they only install on Mac.

Not needed on Windows or Linux where GLFW reads controllers correctly.
"""

import sys
import threading
import time

import hal.simulation
import wpilib


def start_controller_bridge() -> None:
    """Start the SDL2 controller bridge if running on macOS.

    Safe to call on any platform — returns immediately on non-Mac systems.
    Should be called once during ``PhysicsEngine.__init__``.
    """
    if sys.platform != "darwin":
        return

    try:
        import sdl2
    except ImportError:
        wpilib.reportWarning(
            "pysdl2 not installed — Xbox controller input in sim requires "
            "'pip install pysdl2 pysdl2-dll' on macOS"
        )
        return

    # --- Mapping tables: SDL2 game controller → WPILib XboxController ---

    # SDL2 axis constant → WPILib axis index
    axis_map = {
        sdl2.SDL_CONTROLLER_AXIS_LEFTX: 0,        # kLeftX
        sdl2.SDL_CONTROLLER_AXIS_LEFTY: 1,         # kLeftY
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT: 2,   # kLeftTrigger
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT: 3,   # kRightTrigger
        sdl2.SDL_CONTROLLER_AXIS_RIGHTX: 4,        # kRightX
        sdl2.SDL_CONTROLLER_AXIS_RIGHTY: 5,        # kRightY
    }

    # SDL2 button constant → bit index in HAL button bitmask.
    # WPILib buttons are 1-based: bit 0 = button 1 (A), bit 1 = button 2 (B), etc.
    button_map = {
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

    # D-pad buttons for POV conversion (up, down, left, right order)
    dpad_buttons = [
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP,
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN,
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT,
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
    ]

    def _dpad_to_pov(up, down, left, right):
        """Convert four d-pad booleans to a WPILib POV angle (-1 if released)."""
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

        # Open all game-controller-capable devices.
        # First controller → port 0 (driver), second → port 1 (operator).
        controllers = []  # list of (sdl2_gc_handle, wpilib_port)
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
            # No physical controllers found — exit silently so the sim GUI's
            # virtual joystick panel continues to work.
            sdl2.SDL_Quit()
            return

        # Poll loop at ~100 Hz
        while True:
            sdl2.SDL_PumpEvents()

            for gc, port in controllers:
                # Axes (SDL2: -32768..32767 → WPILib: -1.0..1.0)
                for sdl_axis, wpi_axis in axis_map.items():
                    raw = sdl2.SDL_GameControllerGetAxis(gc, sdl_axis)
                    hal.simulation.setJoystickAxis(port, wpi_axis, raw / 32767.0)

                # Buttons → packed bitmask
                buttons = 0
                for sdl_btn, bit_index in button_map.items():
                    if sdl2.SDL_GameControllerGetButton(gc, sdl_btn):
                        buttons |= (1 << bit_index)
                hal.simulation.setJoystickButtonsValue(port, buttons)

                # D-pad → POV angle
                dpad = [
                    bool(sdl2.SDL_GameControllerGetButton(gc, b))
                    for b in dpad_buttons
                ]
                hal.simulation.setJoystickPOV(port, 0, _dpad_to_pov(*dpad))

            hal.simulation.notifyDriverStationNewData()
            time.sleep(0.01)

    t = threading.Thread(
        target=_bridge_thread, daemon=True, name="sdl2-controller-bridge"
    )
    t.start()
