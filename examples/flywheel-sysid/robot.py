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

def GetSparkSignalsVelocityControlConfig(signalConfig: rev.SignalsConfig, periodMs: int) -> rev.SignalsConfig:
    #signalConfig = rev.SignalsConfig()
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
    
    #signalConfig.setpointAlwaysOn(True)
    #signalConfig.setpointPeriodMs(periodMs)
    return signalConfig

def GetSparkConfig(
    config: rev.SparkBaseConfig,
    inverted: bool = False, 
    periodMs: int = 10, 
    idleMode: rev.SparkBaseConfig.IdleMode = rev.SparkBaseConfig.IdleMode.kCoast ) -> rev.SparkBaseConfig:
    #config = rev.SparkBaseConfig()
    config.inverted(inverted)
    config.setIdleMode(idleMode)
    config.voltageCompensation(12.0)
    config.smartCurrentLimit(40)
    #config.apply()
    GetSparkSignalsVelocityControlConfig(config.signals, periodMs)
    return config

def GetFlywheelPidConfig(p : float = 0.0, i : float = 0.0, d : float = 0.0, outputRange : list[float] = [-1.0, 1.0], kV : float = 0.0) -> rev.ClosedLoopConfig:
    pidConfig = rev.ClosedLoopConfig()
    if len(outputRange) != 2:
        raise ValueError("outputRange must be a list of two floats: [minOutput, maxOutput]")
    pidConfig.P(p)
    pidConfig.I(i)
    pidConfig.D(d)
    pidConfig.feedForward.kV(kV)
    pidConfig.minOutput(outputRange[0])
    pidConfig.maxOutput(outputRange[1])
    return pidConfig


class MyRobot(TimedCommandRobot):
    def __init__(self):
        #setup 10ms frames
        super().__init__(period=0.01)
    def robotInit(self):
        flywheelMotors = {}
        motor = rev.SparkFlex(10, rev.SparkLowLevel.MotorType.kBrushless)
        print(motor.configAccessor.signals.getPrimaryEncoderVelocityAlwaysOn())
        config = GetSparkConfig(rev.SparkBaseConfig())
        errror = motor.configure(config, rev.ResetMode.kResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        print(errror)
        print(motor.configAccessor.signals.getPrimaryEncoderVelocityAlwaysOn())
        GetFlywheelPidConfig()
        flywheelMotors["upperFlyWheel"] = motor
        motor = rev.SparkMax(6, rev.SparkLowLevel.MotorType.kBrushless)
        motor.configure(config, rev.ResetMode.kResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        flywheelMotors["lowerFlyWheel"] = motor

        """motor = rev.SparkFlex(14, rev.SparkLowLevel.MotorType.kBrushless)
        motor.configure(config, rev.ResetMode.kResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        flywheelMotors["intakeFlyWheel"] = motor
        """
        self.flywheels = flywheel.FlywheelSysId(flywheelMotors)

        #setup logging
        wpilib.DataLogManager.start()
        urcl.start()
        #urcl.start(motorIdNameMap, wpilib.DataLogManager.getLog())

        sysIdConfig = SysIdRoutine.Config(2, 5, 10.0, None)
        sysIdMechanism = SysIdRoutine.Mechanism(self.flywheels.setMotorVoltage, self.flywheels.sysIdLog, self.flywheels, "Flywheels")
        self.sysId = SysIdRoutine(sysIdConfig, sysIdMechanism)

    
    def teleopInit(self) -> None:
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
        #print(dir(self.flywheels.motors["upperFlyWheel"])PeriodicFrame)
        
    
    def teleopPeriodic(self):
        super().teleopPeriodic()
        
