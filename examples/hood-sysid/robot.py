import wpilib
<<<<<<< HEAD
from urcl import URCL as urcl
=======
>>>>>>> main
import rev

from commands2.sysid import SysIdRoutine
from commands2.button import CommandXboxController
from commands2 import TimedCommandRobot
import commands2

<<<<<<< HEAD
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from config import HoodConfig
from constants.swerve_constants import HoodConstants
from subsystem.mechanisms.shooter.hood import Hood
from utils.passive_range_finder import PassiveRangeFinderCommand

# Hood motor CAN ID
kHoodMotorID = HoodConstants.motorId
=======
from hood import Hood
from passive_range_finder import PassiveRangeFinderCommand

# Inline constants (self-contained for roboRIO deploy)
MOTOR_CAN_ID = 34
POSITION_CONVERSION_FACTOR = 9.53  # From calibration: 20 deg / ~2.1 rotations
MAX_ANGLE_DEGREES = 20.0
PID = (0.3, 0.02, 0)
FEEDFORWARD = (0.4, 0.04, 0, 0)  # kS=0.4 static hold, kG=0.04 gravity
HORIZONTAL_OFFSET_DEGREES = 0.0
>>>>>>> main


class MyRobot(TimedCommandRobot):
    def __init__(self):
        super().__init__(period=0.02)

    def robotInit(self):
<<<<<<< HEAD
        # Create hood motor and subsystem
        self.hood_motor = rev.SparkMax(
            kHoodMotorID,
=======
        # Create adjustable release motor and subsystem
        self.hood_motor = rev.SparkMax(
            MOTOR_CAN_ID,
>>>>>>> main
            rev.SparkLowLevel.MotorType.kBrushless
        )
        self.hood = Hood(
            motor=self.hood_motor,
<<<<<<< HEAD
            position_conversion_factor=HoodConstants.positionConversionFactor,
            max_angle_degrees=HoodConstants.maxAngleDegrees,
            pid=HoodConfig.hoodPID,
            feedforward=HoodConfig.hoodFeedforward,
            horizontal_offset_degrees=HoodConfig.horizontalOffsetDegrees,
=======
            position_conversion_factor=POSITION_CONVERSION_FACTOR,
            max_angle_degrees=MAX_ANGLE_DEGREES,
            pid=PID,
            feedforward=FEEDFORWARD,
            horizontal_offset_degrees=HORIZONTAL_OFFSET_DEGREES,
>>>>>>> main
        )

        # Setup logging
        wpilib.DataLogManager.start()
<<<<<<< HEAD
        urcl.start()

        # Setup SysId routine
        # Config: ramp rate 0.2 V/s, step voltage 4V, timeout 30s
        sysIdConfig = SysIdRoutine.Config(0.2, 4, 30.0, None)
        sysIdMechanism = SysIdRoutine.Mechanism(
            self.hood.setMotorVoltage,
            self.hood.sysIdLog,
            self.hood,
            "Hood"
=======

        # Setup SysId routine
        # Config: ramp rate 0.2 V/s, step voltage 4V, timeout 30s
        sysIdConfig = SysIdRoutine.Config(0.1, 1, 30.0, None)
        sysIdMechanism = SysIdRoutine.Mechanism(
            self.hood._setMotorVoltage,
            self.hood._sysIdLog,
            self.hood,
            "hood"
>>>>>>> main
        )
        self.sysId = SysIdRoutine(sysIdConfig, sysIdMechanism)

    def teleopInit(self) -> None:
        self.controller = CommandXboxController(0)

        # A/B: Quasistatic forward/reverse
        self.controller.a().whileTrue(
<<<<<<< HEAD
            self.hood.sysIdQuasistaticCommand(
=======
            self.hood._sysIdQuasistaticCommand(
>>>>>>> main
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.b().whileTrue(
<<<<<<< HEAD
            self.hood.sysIdQuasistaticCommand(
=======
            self.hood._sysIdQuasistaticCommand(
>>>>>>> main
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

        # X/Y: Dynamic forward/reverse
        self.controller.x().whileTrue(
<<<<<<< HEAD
            self.hood.sysIdDynamicCommand(
=======
            self.hood._sysIdDynamicCommand(
>>>>>>> main
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.y().whileTrue(
<<<<<<< HEAD
            self.hood.sysIdDynamicCommand(
=======
            self.hood._sysIdDynamicCommand(
>>>>>>> main
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

<<<<<<< HEAD
        # Back button: toggle passive range finder (start/stop)
        self.controller.back().toggleOnTrue(
            PassiveRangeFinderCommand(
                self.hood_motor, "Hood", self.hood)
=======
        # Start button: manual position control with right trigger
        self.controller.start().toggleOnTrue(
            self.hood.manualTestCommand(
                self.controller.getRightTriggerAxis)
        )

        # Back button: toggle passive range finder (start/stop)
        self.controller.back().toggleOnTrue(
            PassiveRangeFinderCommand(
                self.hood_motor,
                "AdjustableRelease",
                self.hood,
                zero_on_end=True,
                full_range=MAX_ANGLE_DEGREES)
>>>>>>> main
        )

    def teleopPeriodic(self):
        super().teleopPeriodic()

    def testInit(self):
        super().testInit()
        self.controller = CommandXboxController(0)

        # Test mode: manual position control
        self.controller.a().onTrue(
            commands2.cmd.run(
<<<<<<< HEAD
                lambda: self.hood.setAngleDegrees(0.0), self.hood)
        )
        self.controller.b().onTrue(
            commands2.cmd.run(
                lambda: self.hood.setAngleDegrees(15.0), self.hood)
        )
        self.controller.x().onTrue(
            commands2.cmd.run(
                lambda: self.hood.setAngleDegrees(30.0), self.hood)
=======
                lambda: self.hood.setAngleDegrees(0.0),
                self.hood)
        )
        self.controller.b().onTrue(
            commands2.cmd.run(
                lambda: self.hood.setAngleDegrees(15.0),
                self.hood)
        )
        self.controller.x().onTrue(
            commands2.cmd.run(
                lambda: self.hood.setAngleDegrees(30.0),
                self.hood)
>>>>>>> main
        )

    def testPeriodic(self):
        super().testPeriodic()
