"""
Minimal physics engine that only runs the SDL2 controller bridge on macOS.
No robot simulation — just controller input forwarding for testing.

See utils/sim/sdl2_controller_bridge.py for full documentation.
"""

import sys
sys.path.insert(0, "../..")  # Allow importing from project root

from pyfrc.physics.core import PhysicsInterface
from utils.sim.sdl2_controller_bridge import start_controller_bridge


class PhysicsEngine:
    def __init__(self, physics_controller: PhysicsInterface, robot) -> None:
        start_controller_bridge()

    def update_sim(self, now: float, tm_diff: float) -> None:
        pass
