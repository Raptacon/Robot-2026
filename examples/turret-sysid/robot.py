import wpilib
from urcl import URCL as urcl
import rev
import turret

from commands2.sysid import SysIdRoutine
from commands2.button import CommandXboxController
from commands2 import TimedCommandRobot
import commands2

# Turret motor CAN ID
kTurretMotorID = 40

# Turret configuration
# 11:1 gear ratio: 1 motor rotation = 360/11 degrees turret rotation
kPositionConversionFactor = 360 / 11  # degrees per motor rotation
kMinSoftLimit = -90.0  # degrees
kMaxSoftLimit = 90.0   # degrees


class MyRobot(TimedCommandRobot):
    def __init__(self):
        # Setup 20ms frames
        super().__init__(period=0.02)

    def robotInit(self):
        # Create turret motor and subsystem
        motor = rev.SparkMax(
            kTurretMotorID,
            rev.SparkLowLevel.MotorType.kBrushless
        )
        self.turret = turret.Turret(
            motor=motor,
            position_conversion_factor=kPositionConversionFactor,
            min_soft_limit=kMinSoftLimit,
            max_soft_limit=kMaxSoftLimit
        )

        # Setup logging
        wpilib.DataLogManager.start()
        urcl.start()

        # Setup SysId routine
        # Config: ramp rate 2 V/s, step voltage 5V, timeout 10s
        sysIdConfig = SysIdRoutine.Config(0.5, 5, 10.0, None)
        sysIdMechanism = SysIdRoutine.Mechanism(
            self.turret.setMotorVoltage,
            self.turret.sysIdLog,
            self.turret,
            "Turret"
        )
        self.sysId = SysIdRoutine(sysIdConfig, sysIdMechanism)

    def teleopInit(self) -> None:
        self.controller = CommandXboxController(0)

        # A/B: Quasistatic forward/reverse
        self.controller.a().whileTrue(
            self.turret.sysIdQuasistaticCommand(
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.b().whileTrue(
            self.turret.sysIdQuasistaticCommand(
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

        # X/Y: Dynamic forward/reverse
        self.controller.x().whileTrue(
            self.turret.sysIdDynamicCommand(
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.y().whileTrue(
            self.turret.sysIdDynamicCommand(
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

    def teleopPeriodic(self):
        super().teleopPeriodic()

    def testInit(self):
        super().testInit()
        self.controller = CommandXboxController(0)
        # A/B: Quasistatic forward/reverse
        self.controller.a().onTrue(
            commands2.cmd.run(lambda: self.turret.setPosition(-90.0), self.turret)
        )

        self.controller.b().onTrue(
            commands2.cmd.run(lambda: self.turret.setPosition(0), self.turret)
        )

        # X/Y: Dynamic forward/reverse
        self.controller.x().onTrue(
            commands2.cmd.run(lambda: self.turret.setPosition(90.0), self.turret)
        )

        self.setPositionMagic = 0.0
        self.setPositionMagicSign = 1
        self.setPositionMagicIncrement = 3.6
        
    def testPeriodic(self):
        super().testPeriodic()
        if self.controller._hid.getYButton():
            self.setPositionMagic += (self.setPositionMagicSign * self.setPositionMagicIncrement)
            if self.setPositionMagic > 90.0:
                self.setPositionMagic = 90.0
                self.setPositionMagicSign = -1
            elif self.setPositionMagic < -90.0:
                self.setPositionMagic = -90.0
                self.setPositionMagicSign = 1
            print(f"setPositionMagic: {self.setPositionMagic : .1f} deg")
            self.turret.setPosition(self.setPositionMagic)
            print("y button pressed")
        if self.controller._hid.getStartButtonPressed():
            print("start button pressed, calibration started")
            self.turret.calibrationInit(10, 0.1, 5, 3.6)
        
    