import wpilib
from urcl import URCL as urcl
import rev
import commands2
import intake_pos

from commands2.sysid import SysIdRoutine
from commands2.button import CommandXboxController
from commands2 import TimedCommandRobot

# -------------------------------------------------------------------------
# Intake arm configuration
# -------------------------------------------------------------------------

# SparkMax CAN ID for the intake position motor
kIntakePosMotorID = 20

# Gear ratio conversion factor: motor rotations -> arm degrees.
# IMPORTANT: Measure your actual gear ratio and update this value.
# 10:1 reduction -> 360.0 / 10.0 = 36.0 degrees per motor rotation
kPositionConversionFactor = 360.0 / 10.0  # degrees per motor rotation

# Arm travel range in degrees.  Set these to the expected mechanical limits.
# Calibration will discover the actual hard stops and update soft limits.
kMinSoftLimit = 0.0    # degrees — stowed position
kMaxSoftLimit = 120.0  # degrees — fully deployed

# -------------------------------------------------------------------------
# SysId routine configuration
# -------------------------------------------------------------------------
# Quasistatic ramp rate (V/s): how slowly voltage increases during ramp test
kSysIdQuasiRampRate = 0.5
# Dynamic step voltage (V): voltage applied during step test
kSysIdDynamicStepV = 3.0
# Timeout per test (s)
kSysIdTimeout = 10.0

# -------------------------------------------------------------------------
# Calibration configuration
# -------------------------------------------------------------------------
# Run calibration at 5% motor power to safely find hard stops
kCalibrationPowerPct = 0.05
# Current limit during calibration (amps)
kCalibrationCurrentLimit = 10.0
# Max time per homing phase before timeout (seconds)
kCalibrationTimeout = 15.0


class MyRobot(TimedCommandRobot):
    """
    Sample robot for intake arm position control, calibration, and SysId.

    Workflow:
      1. Enable robot in teleop mode.
      2. Press Start to run calibration at 5% power.  The arm drives gently
         to both hard stops to discover the mechanical range.
      3. Wait for /IntakePos/isCalibrated = True on the dashboard.
      4. Use A/B (quasistatic) and X/Y (dynamic) to collect SysId data.
         These buttons are gated and will not fire until calibrated.
      5. After SysId: update kS/kV and PID gains via NT, then enable
         profiled position control with full velocity limits.

    Test mode:
      A = stowed (0 deg), B = mid (60 deg), X = deployed (120 deg)
      Start = run calibration
    """

    def __init__(self):
        super().__init__(period=0.02)  # 20ms / 50Hz

    def robotInit(self):
        # Create motor and subsystem
        motor = rev.SparkMax(
            kIntakePosMotorID,
            rev.SparkLowLevel.MotorType.kBrushless,
        )
        self.intake = intake_pos.IntakePos(
            motor=motor,
            position_conversion_factor=kPositionConversionFactor,
            min_soft_limit=kMinSoftLimit,
            max_soft_limit=kMaxSoftLimit,
        )

        # Data logging
        wpilib.DataLogManager.start()
        urcl.start()

        # SysId routine
        # Low ramp rate and step voltage since intake arm has limited travel
        sysIdConfig = SysIdRoutine.Config(
            kSysIdQuasiRampRate,
            kSysIdDynamicStepV,
            kSysIdTimeout,
            None,
        )
        sysIdMechanism = SysIdRoutine.Mechanism(
            self.intake.setMotorVoltage,
            self.intake.sysIdLog,
            self.intake,
            "IntakePos",
        )
        self.sysId = SysIdRoutine(sysIdConfig, sysIdMechanism)

    def teleopInit(self) -> None:
        self.controller = CommandXboxController(0)

        # Gate SysId commands on calibration being complete
        calibrated = commands2.button.Trigger(
            lambda: self.intake._is_calibrated
        )

        # Start: run calibration at 5% power
        self.controller.start().onTrue(
            commands2.cmd.runOnce(
                lambda: self.intake.calibrationInit(
                    max_current=kCalibrationCurrentLimit,
                    max_power_pct=kCalibrationPowerPct,
                    max_homing_time=kCalibrationTimeout,
                ),
                self.intake,
            )
        )

        # A/B: Quasistatic forward/reverse (requires calibration)
        self.controller.a().and_(calibrated).whileTrue(
            self.intake.sysIdQuasistaticCommand(
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.b().and_(calibrated).whileTrue(
            self.intake.sysIdQuasistaticCommand(
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

        # X/Y: Dynamic forward/reverse (requires calibration)
        self.controller.x().and_(calibrated).whileTrue(
            self.intake.sysIdDynamicCommand(
                SysIdRoutine.Direction.kForward, self.sysId
            )
        )
        self.controller.y().and_(calibrated).whileTrue(
            self.intake.sysIdDynamicCommand(
                SysIdRoutine.Direction.kReverse, self.sysId
            )
        )

    def teleopPeriodic(self):
        super().teleopPeriodic()

    def testInit(self):
        super().testInit()
        self.controller = CommandXboxController(0)

        # Y / Start: calibration at 5% power
        # Y works with a generic 4-button sim joystick; Start requires XInput type
        def _cal_cmd():
            return commands2.cmd.runOnce(
                lambda: self.intake.calibrationInit(
                    max_current=kCalibrationCurrentLimit,
                    max_power_pct=kCalibrationPowerPct,
                    max_homing_time=kCalibrationTimeout,
                ),
                self.intake,
            )
        self.controller.y().onTrue(_cal_cmd())
        if not wpilib.RobotBase.isSimulation():
            self.controller.start().onTrue(_cal_cmd())

        # Position presets (only useful after calibration)
        self.controller.a().onTrue(
            commands2.cmd.runOnce(
                lambda: self.intake.setPosition(kMinSoftLimit), self.intake
            )
        )
        self.controller.b().onTrue(
            commands2.cmd.runOnce(
                lambda: self.intake.setPosition(
                    (kMinSoftLimit + kMaxSoftLimit) / 2.0
                ),
                self.intake,
            )
        )
        self.controller.x().onTrue(
            commands2.cmd.runOnce(
                lambda: self.intake.setPosition(kMaxSoftLimit), self.intake
            )
        )

    def testPeriodic(self):
        super().testPeriodic()
