"""
Minimal test robot to verify Xbox controller inputs are received on Mac sim.
Prints axis and button values to console every 500ms.
"""

import wpilib


class ControllerTestRobot(wpilib.TimedRobot):
    def robotInit(self):
        self.controller = wpilib.XboxController(0)
        self.timer = wpilib.Timer()
        self.timer.start()

    def teleopPeriodic(self):
        if self.timer.advanceIfElapsed(0.5):
            lx = self.controller.getLeftX()
            ly = self.controller.getLeftY()
            rx = self.controller.getRightX()
            ry = self.controller.getRightY()
            lt = self.controller.getLeftTriggerAxis()
            rt = self.controller.getRightTriggerAxis()
            a = self.controller.getAButton()
            b = self.controller.getBButton()
            x = self.controller.getXButton()
            y = self.controller.getYButton()
            lb = self.controller.getLeftBumper()
            rb = self.controller.getRightBumper()
            pov = self.controller.getPOV()

            print(
                f"Axes: LX={lx:+.2f} LY={ly:+.2f} RX={rx:+.2f} RY={ry:+.2f} "
                f"LT={lt:.2f} RT={rt:.2f} | "
                f"Buttons: A={a} B={b} X={x} Y={y} LB={lb} RB={rb} | "
                f"POV={pov}"
            )


if __name__ == "__main__":
    wpilib.run(ControllerTestRobot)
