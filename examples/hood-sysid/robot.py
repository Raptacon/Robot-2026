import wpilib
from urcl import URCL as urcl
import rev

from commands2.sysid import SysIdRoutine
from commands2.button import CommandXboxController
from commands2 import TimedCommandRobot
import commands2

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from config import HoodConfig
from constants.swerve_constants import HoodConstants
from subsystem.shooter.hood import Hood
from utils.passive_range_finder import PassiveRangeFinderCommand

# Hood motor CAN ID
kHoodMotorID = HoodConstants.motorId


class MyRobot(TimedCommandRobot):
    def __init__(self):
        super().__init__(period=0.02)

    def robotInit(self):
        # Create hood motor and subsystem
        self.hood_motor = rev.SparkMax(
            kHoodMotorID,
            rev.SparkLowLevel.MotorType.kBrushless
        )
        self.hood = Hood(
            motor=self.hood_motor,
            position_conversion_factor=HoodConstants.positionConversionFactor,
            max_angle_degrees=HoodConstants.maxAngleDegrees,
            pid=HoodConfig.hoodPID,
            feedforward=HoodConfig.hoodFeedforward,
            horizontal_offset_degrees=HoodConfig.horizontalOffsetDegrees,
        )

        # Setup logging
        wpilib.DataLogManager.start()
        urcl.start()

        # Setup SysId routine
        # Config: ramp rate 0.2 V/s, step voltage 4V, timeout 30s
        sysIdConfig = SysIdRoutine.Config(0.2, 4, 30.0, None)
        sysIdMechanism = SysIdRoutine.Mechanism(
            self.hood.setMotorVoltage,
            self.hood.sysIdLog,
            self.hood,
            "Hood"
        )
        self.sysId = SysIdRoutine(sysIdConfig, sysIdMechanism)

    def teleopInit(self) -> None:
        self.controller = CommandXboxController(0)

        # A/B: Quasistatic forward/reverse
        self.controller.a().whileTrue(
            self.hood.sysIdQuasistaticCommand(
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.b().whileTrue(
            self.hood.sysIdQuasistaticCommand(
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

        # X/Y: Dynamic forward/reverse
        self.controller.x().whileTrue(
            self.hood.sysIdDynamicCommand(
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.y().whileTrue(
            self.hood.sysIdDynamicCommand(
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

        # Back button: toggle passive range finder (start/stop)
        self.controller.back().toggleOnTrue(
            PassiveRangeFinderCommand(
                self.hood_motor, "Hood", self.hood)
        )

    def teleopPeriodic(self):
        super().teleopPeriodic()

    def testInit(self):
        super().testInit()
        self.controller = CommandXboxController(0)

        # Test mode: manual position control
        self.controller.a().onTrue(
            commands2.cmd.run(
                lambda: self.hood.setAngleDegrees(0.0), self.hood)
        )
        self.controller.b().onTrue(
            commands2.cmd.run(
                lambda: self.hood.setAngleDegrees(15.0), self.hood)
        )
        self.controller.x().onTrue(
            commands2.cmd.run(
                lambda: self.hood.setAngleDegrees(30.0), self.hood)
        )

    def testPeriodic(self):
        super().testPeriodic()
