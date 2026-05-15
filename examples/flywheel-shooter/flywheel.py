from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
import rev
from typing import Callable

class FlywheelSysId(Subsystem):
    def __init__(self, motors: list[rev.SparkMax]):
        super().__init__()
        self.motors = motors

    def setMotorVoltage(self, output: float):
        for name, motor in self.motors.items():
            motor.setVoltage(output)


    def runFlywheelCommand(self, speed: Callable[[], float]) -> Command:
        return self.setMotorVoltage(speed())

    def sysIdQuasistaticCommand(self, direction: SysIdRoutine.Direction, sysIdRoutine: SysIdRoutine) -> Command:
        value = sysIdRoutine.quasistatic(direction)
        print(f"Quasistatic Command Value: {value}, Direction: {direction}")
        return value
    def sysIdDynamicCommand(self, direction: SysIdRoutine.Direction, sysIdRoutine: SysIdRoutine) -> Command:
        value = sysIdRoutine.dynamic(direction)
        print(f"Dynamic Command Value: {value}, Direction: {direction}")
        return sysIdRoutine.dynamic(direction)
