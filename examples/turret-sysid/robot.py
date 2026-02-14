import wpilib
from urcl import URCL as urcl
import rev
import turret

from commands2.sysid import SysIdRoutine
from commands2.button import CommandXboxController
from commands2 import TimedCommandRobot

# Turret motor CAN ID
kTurretMotorID = 40

# Turret configuration
# 100:1 gear ratio: 1 motor rotation = 3.6 degrees turret rotation
kPositionConversionFactor = 3.6  # degrees per motor rotation
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
        sysIdConfig = SysIdRoutine.Config(2, 5, 10.0, None)
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
