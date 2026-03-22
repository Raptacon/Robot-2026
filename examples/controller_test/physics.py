"""
Minimal physics engine that only runs the SDL2 controller bridge on macOS.
"""

import sys
import time

import hal.simulation
import wpilib
from pyfrc.physics.core import PhysicsInterface

_sdl2 = None
_gc = None
_port = 0
_AXIS_MAP = {}
_BUTTON_MAP = {}
_DPAD = []


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


class PhysicsEngine:
    def __init__(self, physics_controller: PhysicsInterface, robot) -> None:
        global _sdl2, _gc, _AXIS_MAP, _BUTTON_MAP, _DPAD

        self._sdl2_ok = False
        if sys.platform != "darwin":
            return

        try:
            import sdl2
            _sdl2 = sdl2
        except ImportError:
            wpilib.reportWarning(
                "pysdl2 not installed — 'pip install pysdl2 pysdl2-dll'"
            )
            return

        _AXIS_MAP = {
            sdl2.SDL_CONTROLLER_AXIS_LEFTX: 0,
            sdl2.SDL_CONTROLLER_AXIS_LEFTY: 1,
            sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT: 2,
            sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT: 3,
            sdl2.SDL_CONTROLLER_AXIS_RIGHTX: 4,
            sdl2.SDL_CONTROLLER_AXIS_RIGHTY: 5,
        }
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

        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_MFI, b"1")
        sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER)

        for _ in range(20):
            sdl2.SDL_PumpEvents()
            time.sleep(0.05)

        for idx in range(sdl2.SDL_NumJoysticks()):
            if sdl2.SDL_IsGameController(idx):
                _gc = sdl2.SDL_GameControllerOpen(idx)
                break

        if not _gc:
            print("SDL2 bridge: no game controllers found")
            return

        gc_name = sdl2.SDL_GameControllerName(_gc)
        if gc_name and isinstance(gc_name, bytes):
            gc_name = gc_name.decode()
        wpilib.reportWarning(f"SDL2 bridge: '{gc_name}' → port {_port}")
        self._sdl2_ok = True
        self._tick = 0

    def update_sim(self, now: float, tm_diff: float) -> None:
        if not self._sdl2_ok:
            return

        _sdl2.SDL_PumpEvents()

        hal.simulation.setJoystickAxisCount(_port, 6)
        hal.simulation.setJoystickButtonCount(_port, 10)
        hal.simulation.setJoystickPOVCount(_port, 1)

        for sdl_axis, wpi_axis in _AXIS_MAP.items():
            raw = _sdl2.SDL_GameControllerGetAxis(_gc, sdl_axis)
            hal.simulation.setJoystickAxis(_port, wpi_axis, raw / 32767.0)

        buttons = 0
        for sdl_btn, bit_index in _BUTTON_MAP.items():
            if _sdl2.SDL_GameControllerGetButton(_gc, sdl_btn):
                buttons |= (1 << bit_index)
        hal.simulation.setJoystickButtonsValue(_port, buttons)

        dpad = [
            bool(_sdl2.SDL_GameControllerGetButton(_gc, b))
            for b in _DPAD
        ]
        hal.simulation.setJoystickPOV(_port, 0, _dpad_to_pov(*dpad))

        hal.simulation.notifyDriverStationNewData()

        self._tick += 1
        if self._tick % 100 == 0:
            lx = _sdl2.SDL_GameControllerGetAxis(_gc, _sdl2.SDL_CONTROLLER_AXIS_LEFTX) / 32767.0
            ly = _sdl2.SDL_GameControllerGetAxis(_gc, _sdl2.SDL_CONTROLLER_AXIS_LEFTY) / 32767.0
            print(f"SDL2 bridge tick {self._tick}: LX={lx:+.2f} LY={ly:+.2f} buttons=0x{buttons:04x}")
