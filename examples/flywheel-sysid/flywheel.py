from typing import Callable
from commands2 import Command, Subsystem
from commands2.sysid import SysIdRoutine
from wpilib.sysid import SysIdRoutineLog
import rev

#sample feedforad value
#0.017981
#Feed forard
#1.5606034333275533206173053580718e-4 = 0.00015606034333275534
#kP 3
#kd - 0
#ki 0.005 (reduce steady state error)
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

    def sysIdLog(self, sys_id_routine: SysIdRoutineLog) -> None:
        for name, motor in self.motors.items():
            motor_log = sys_id_routine.motor(name)
            #gather data
            #angular veloicity and andgulat psotion
            angular_velocity = motor.getEncoder().getVelocity() * (2 * 3.141592653589793 / 60)  # Convert RPM to rad/s
            angular_position = motor.getEncoder().getPosition() * (2 * 3.141592653589793 / 60)  # Convert rotations to rad
            current = motor.getOutputCurrent()
            battery_voltage = motor.getBusVoltage()
            motor_temp = motor.getMotorTemperature()
            applied_voltage = motor.getAppliedOutput() * battery_voltage

            #not included velocity acceleration, angularAcceleration, angularPosition,
            motor_log.angularVelocity(angular_velocity)
            motor_log.angularPosition(angular_position)
            motor_log.current(current)
            motor_log.voltage(applied_voltage)
            #extra data
            motor_log.value("temperature", motor_temp, "C")
            motor_log.value("busVoltage", battery_voltage, "V")
