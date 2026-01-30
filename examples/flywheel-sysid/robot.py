import wpilib
from urcl import URCL as urcl
import rev
import flywheel

from commands2.sysid import SysIdRoutine
from commands2.button import CommandXboxController
from commands2 import TimedCommandRobot

kUpperFlywheelMotorID = 1
kLowerFlywheelMotorID = 2
kIntakeFlywheelMotorID = 3
motorIdNameMap = {
    kUpperFlywheelMotorID: "UpperFlyWheel",
    kLowerFlywheelMotorID: "LowerFlyWheel",
    kIntakeFlywheelMotorID: "IntakeFlyWheel",
}

def GetSparkSignalsConfig(periodMs: int) -> rev.SignalsConfig:
    signalConfig = rev.SignalsConfig()
    signalConfig.analogVoltageAlwaysOn(True)
    signalConfig.analogPositionPeriodMs(periodMs)
    signalConfig.busVoltageAlwaysOn(True)
    signalConfig.busVoltagePeriodMs(periodMs)
    signalConfig.appliedOutputAlwaysOn(True)
    signalConfig.appliedOutputPeriodMs(periodMs)
    signalConfig.motorTemperatureAlwaysOn(True)
    signalConfig.motorTemperaturePeriodMs(periodMs)
    signalConfig.outputCurrentAlwaysOn(True)
    signalConfig.outputCurrentPeriodMs(periodMs)
    signalConfig.primaryEncoderVelocityAlwaysOn(True)
    signalConfig.primaryEncoderVelocityPeriodMs(periodMs)
    signalConfig.setpointAlwaysOn(True)
    signalConfig.setpointPeriodMs(periodMs)
    return signalConfig

def GetSparkConfig(inverted: bool = False, 
                   periodMs: int = 20, 
                   idleMode: rev.SparkBaseConfig.IdleMode = rev.SparkBaseConfig.IdleMode.kCoast ) -> rev.SparkBaseConfig:
    config = rev.SparkBaseConfig()
    config.inverted(inverted)
    config.setIdleMode(idleMode)
    config.voltageCompensation(12.0)
    config.apply(GetSparkSignalsConfig(periodMs))
    return config

class MyRobot(TimedCommandRobot):
    def robotInit(self):
        flywheelMotors = {}
        motor = rev.SparkFlex(1, rev.SparkLowLevel.MotorType.kBrushless)
        motor.configure(GetSparkConfig(), rev.ResetMode.kResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        flywheelMotors["upperFlyWheel"] = motor
        motor = rev.SparkFlex(2, rev.SparkLowLevel.MotorType.kBrushless)
        motor.configure(GetSparkConfig(), rev.ResetMode.kResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        flywheelMotors["lowerFlyWheel"] = motor

        motor = rev.SparkMax(3, rev.SparkLowLevel.MotorType.kBrushless)
        motor.configure(GetSparkConfig(), rev.ResetMode.kResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        flywheelMotors["intakeFlyWheel"] = motor

        self.flywheels = flywheel.FlywheelSysId(flywheelMotors)

        #setup logging
        wpilib.DataLogManager.start()
        urcl.start(motorIdNameMap)

        sysIdConfig = SysIdRoutine.Config(1, 7, 10.0, None)
        sysIdMechanism = SysIdRoutine.Mechanism(self.flywheels.setMotorVoltage, self.sysIdNullLog, self.flywheels, "Flywheels")
        self.sysId = SysIdRoutine(sysIdConfig, sysIdMechanism)

        self.controller = CommandXboxController(0)

        self.controller.a().whileTrue(
            self.flywheels.sysIdQuasistaticCommand(SysIdRoutine.Direction.kForward, self.sysId)
        )
        self.controller.b().whileTrue(
            self.flywheels.sysIdQuasistaticCommand(SysIdRoutine.Direction.kReverse, self.sysId)
        )
        self.controller.x().whileTrue(
            self.flywheels.sysIdDynamicCommand(SysIdRoutine.Direction.kForward, self.sysId)
        )
        self.controller.y().whileTrue(
            self.flywheels.sysIdDynamicCommand(SysIdRoutine.Direction.kReverse, self.sysId)
        )

    def sysIdNullLog(self, sys_id_routine: SysIdRoutineLog) -> None:
        pass
