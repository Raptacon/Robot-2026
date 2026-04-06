import wpilib
import rev

from commands2.sysid import SysIdRoutine
from commands2.button import CommandXboxController
from commands2 import TimedCommandRobot
import commands2

from hood import Hood
from passive_range_finder import PassiveRangeFinderCommand

# Inline constants (self-contained for roboRIO deploy)
MOTOR_CAN_ID = 34
POSITION_CONVERSION_FACTOR = 9.53  # From calibration: 20 deg / ~2.1 rotations
MAX_ANGLE_DEGREES = 20.0
PID = (0.3, 0.02, 0)
FEEDFORWARD = (0.4, 0.04, 0, 0)  # kS=0.4 static hold, kG=0.04 gravity
HORIZONTAL_OFFSET_DEGREES = 0.0


class MyRobot(TimedCommandRobot):
    def __init__(self):
        super().__init__(period=0.02)

    def robotInit(self):
        # Create adjustable release motor and subsystem
        self.adjustableRelease_motor = rev.SparkMax(
            MOTOR_CAN_ID,
            rev.SparkLowLevel.MotorType.kBrushless
        )
        self.adjustableRelease = Hood(
            motor=self.adjustableRelease_motor,
            position_conversion_factor=POSITION_CONVERSION_FACTOR,
            max_angle_degrees=MAX_ANGLE_DEGREES,
            pid=PID,
            feedforward=FEEDFORWARD,
            horizontal_offset_degrees=HORIZONTAL_OFFSET_DEGREES,
        )

        # Setup logging
        wpilib.DataLogManager.start()

        # Setup SysId routine
        # Config: ramp rate 0.2 V/s, step voltage 4V, timeout 30s
        sysIdConfig = SysIdRoutine.Config(0.1, 1, 30.0, None)
        sysIdMechanism = SysIdRoutine.Mechanism(
            self.adjustableRelease.setMotorVoltage,
            self.adjustableRelease.sysIdLog,
            self.adjustableRelease,
            "hood"
        )
        self.sysId = SysIdRoutine(sysIdConfig, sysIdMechanism)

    def teleopInit(self) -> None:
        self.controller = CommandXboxController(0)

        # A/B: Quasistatic forward/reverse
        self.controller.a().whileTrue(
            self.adjustableRelease.sysIdQuasistaticCommand(
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.b().whileTrue(
            self.adjustableRelease.sysIdQuasistaticCommand(
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

        # X/Y: Dynamic forward/reverse
        self.controller.x().whileTrue(
            self.adjustableRelease.sysIdDynamicCommand(
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.y().whileTrue(
            self.adjustableRelease.sysIdDynamicCommand(
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

        # Start button: manual position control with right trigger
        self.controller.start().toggleOnTrue(
            self.adjustableRelease.manualTestCommand(
                self.controller.getRightTriggerAxis)
        )

        # Back button: toggle passive range finder (start/stop)
        self.controller.back().toggleOnTrue(
            PassiveRangeFinderCommand(
                self.adjustableRelease_motor,
                "AdjustableRelease",
                self.adjustableRelease,
                zero_on_end=True,
                full_range=MAX_ANGLE_DEGREES)
        )

    def teleopPeriodic(self):
        super().teleopPeriodic()

    def testInit(self):
        super().testInit()
        self.controller = CommandXboxController(0)

        # Test mode: manual position control
        self.controller.a().onTrue(
            commands2.cmd.run(
                lambda: self.adjustableRelease.setAngleDegrees(0.0),
                self.adjustableRelease)
        )
        self.controller.b().onTrue(
            commands2.cmd.run(
                lambda: self.adjustableRelease.setAngleDegrees(15.0),
                self.adjustableRelease)
        )
        self.controller.x().onTrue(
            commands2.cmd.run(
                lambda: self.adjustableRelease.setAngleDegrees(30.0),
                self.adjustableRelease)
        )

    def testPeriodic(self):
        super().testPeriodic()
