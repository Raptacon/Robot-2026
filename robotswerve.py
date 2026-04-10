"""
Container to hold the main robot code.

## Controller Map

![Driver Controller](./assets/2026bot_controller_map_page1.png)

![Operator Controller](./assets/2026bot_controller_map_page2.png)
"""

# Native imports
import json
import os
from pathlib import Path
from typing import Callable

# Internal imports
from config import HoodConfig
import constants.swerve_constants as consts
from data.telemetry import Telemetry
import commands.auto.pid_to_angle
import commands.ball_transport
import commands.default_swerve_drive
import commands.intake_commands
import commands.shooter_commands
import subsystem
import subsystem.drivetrain.swerve_drivetrain
import subsystem.mechanisms.shooter
from utils.input import InputFactory
from utils.odometry_logic_2026 import determineShooterTargets2026

# Third-party imports
import commands2
import wpilib
from commands2.button import Trigger
from pathplannerlib.auto import AutoBuilder
from wpimath.geometry import Rotation2d

class RobotSwerve:
    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        # networktables setup
        self.field = wpilib.Field2d()
        wpilib.SmartDashboard.putData("Field", self.field)

        # Subsystem instantiation
        self.drivetrain = subsystem.drivetrain.swerve_drivetrain.SwerveDrivetrain()
        self.shooter = subsystem.mechanisms.shooter.Shooter()
        self.feed = subsystem.mechanisms.shooter.Feed()
        self.hood = subsystem.mechanisms.shooter.createHood(consts.HoodConstants, HoodConfig)
        self.hood.setShooter(self.shooter)
        self.hopper = subsystem.Hopper()
        self.intake_position = subsystem.IntakePosition()
        self.intake_roller = subsystem.IntakeRoller()

        # Alliance instantiation
        self.updateAlliance()

        # Initialize timer
        self.timer = wpilib.Timer()
        self.timer.start()

        # HID setup — config-driven via InputFactory
        wpilib.DriverStation.silenceJoystickConnectionWarning(True)
        self.factory = InputFactory(config_path="data/inputs/2026bot.yaml")

        # Speed toggle state
        self._drive_scale_slow = 0.25
        self._drive_scale_fast = 1
        self._drive_is_slow = False

        # TODO: Move input retrieval and binding into commands/{subsystem}_controls.py
        # files as part of the subsystem registry refactor. Each subsystem's controls
        # module should own its own factory.get*() calls and command wiring.
        self._configure_controls()

        # Autonomous setup
        self.auto_command = None
        self.auto_chooser = AutoBuilder.buildAutoChooser()
        wpilib.SmartDashboard.putData("Select auto routine", self.auto_chooser)

        # Telemetry setup
        wpilib.SmartDashboard.putNumber("Drivetrain speed", self._drive_scale_fast)
        self._enable_telemetry = wpilib.SmartDashboard.getBoolean("enableTelemetry", True)
        if self._enable_telemetry:
            self.telemetry = Telemetry(
                driveTrain=self.drivetrain,
                driverController=self.factory.getController(0),
                mechController=self.factory.getController(1),
            )

        wpilib.SmartDashboard.putString("Robot Version", self.getDeployInfo("git-hash"))
        wpilib.SmartDashboard.putString("Git Branch", self.getDeployInfo("git-branch"))
        wpilib.SmartDashboard.putString(
            "Deploy Host", self.getDeployInfo("deploy-host")
        )
        wpilib.SmartDashboard.putString(
            "Deploy User", self.getDeployInfo("deploy-user")
        )

        # Update drivetrain motor idle modes 3 seconds after the robot has been disabled.
        # to_break should be False at competitions where the robot is turned off between matches
        Trigger(is_disabled()).debounce(3).onTrue(
            commands2.cmd.runOnce(
                self.drivetrain.set_motor_stop_modes(
                    to_drive=True, to_break=True, all_motor_override=True, burn_flash=True
                ),
                self.drivetrain
            )
        )


    def robotPeriodic(self):
        if self._enable_telemetry and self.telemetry:
            self.telemetry.runDefaultDataCollections()

        self.field.setRobotPose(self.drivetrain.current_pose())

    def disabledInit(self):
        self.updateAlliance()
        self.drivetrain.set_motor_stop_modes(to_drive=True, to_break=True, all_motor_override=True, burn_flash=False)
        self.drivetrain.stop_driving()

        self.shooter.setRPM(0)
        self.shooter.resetOffset()
        self.feed.stop()

        self.hopper.stop()
        self.intake_roller.stop()

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        self.updateAlliance()
        self.auto_command = self.auto_chooser.getSelected()
        if self.auto_command:
            self.auto_command.schedule()
        else:
            self.drivetrain.reset_pose_estimator(self.drivetrain.get_default_starting_pose())

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        self.updateAlliance()
        if self.auto_command:
            self.auto_command.cancel()

        self.drivetrain.setDefaultCommand(
            commands.default_swerve_drive.DefaultDrive(
                self.drivetrain,
                self.translate_x,
                self.translate_y,
                self.rotate,
                lambda: not self.robot_relative_btn()
            )
        )

        self.shooter.setDefaultCommand(commands2.cmd.select(
            {
                "autoRPM": commands2.cmd.run(
                    lambda: self.shooter.setRpmUsingLookup(
                        self.shooter.calculateRangeFromOdometry(
                            self.drivetrain.current_pose,
                            lambda: determineShooterTargets2026(self.drivetrain.current_pose, self.alliance)
                        )
                    ),
                    self.shooter
                ),
                "fixedRPM": commands2.cmd.run(lambda: self.shooter.setRpmAtFixedPosition(), self.shooter)
            },
            self.shooter.getFlywheelMode
        ))

        # Hood default: set angle from shooter's distance-based lookup
        self.hood.setDefaultCommand(self.hood.autoAngleCommand())
            

    def teleopPeriodic(self):
        pass

    def testInit(self):
        #TODO Move to NT listener on change listener
        self.updateAlliance()
        commands2.CommandScheduler.getInstance().cancelAll()
        self.drivetrain.setDefaultCommand(
            commands.default_swerve_drive.DefaultDrive(
                self.drivetrain,
                self.translate_x,
                self.translate_y,
                self.rotate,
                lambda: not self.robot_relative_btn()
            )
        )
        commands2.cmd.run(lambda: self.drivetrain.drive(2, 0, 0, False), self.drivetrain).withTimeout(5).schedule()

        # Hood manual test: trigger analog overrides safety for manual control
        self.hood.setDefaultCommand(
            self.hood.manualTestCommand(self.hood_angle_input))

    def testPeriodic(self):
        pass

    def _configure_controls(self) -> None:
        """Retrieve managed inputs from the factory and wire command bindings.

        TODO: Move into commands/{subsystem}_controls.py files as part of the
        subsystem registry refactor. Each subsystem's controls module would
        call register_controls(subsystem, container) and own its own
        factory.get*() calls and command wiring.
        """
        # Managed drive inputs
        self.translate_x = self.factory.getAnalog("drivetrain.translate_x")
        self.translate_y = self.factory.getAnalog("drivetrain.translate_y")
        self.rotate = self.factory.getAnalog("drivetrain.rotate")
        self.robot_relative_btn = self.factory.getRawButton("drivetrain.robot_relative")

        # Cancel-all: event-driven via Trigger instead of polling
        self.factory.getButton("drivetrain.cancel_all").onTrue(
            commands2.cmd.runOnce(
                lambda: commands2.CommandScheduler.getInstance().cancelAll()
            )
        )

        # Speed toggle: Y button switches between slow and fast scale
        self.factory.getButton("drivetrain.speed_toggle").onTrue(
            commands2.cmd.runOnce(self._toggle_drive_scale)
        )

        # Auto-rotate: rotate the drivetrain until it faces
        self.factory.getButton("drivetrain.auto_align").whileTrue(
            commands.auto.pid_to_angle.PIDAlignToTarget(
                self.drivetrain,
                lambda: determineShooterTargets2026(self.drivetrain.current_pose, self.alliance),
                self.translate_x,
                self.translate_y,
                lambda: not self.robot_relative_btn(),
                alignment_angle=Rotation2d.fromDegrees(180)
            )
        )

        # Shooter inputs
        self.factory.getButton("shooter.increment_RPM").onTrue(
            commands2.cmd.runOnce(lambda: self.shooter.modifyOffset(consts.PancakeShooterConstants.shooterOffsetDelta), self.shooter)
        )
        self.factory.getButton("shooter.decrement_RPM").onTrue(
            commands2.cmd.runOnce(lambda: self.shooter.modifyOffset(-consts.PancakeShooterConstants.shooterOffsetDelta), self.shooter)
        )
        self.factory.getButton("shooter.reset_RPM_offset").onTrue(
            commands2.cmd.runOnce(self.shooter.resetOffset, self.shooter)
        )
        self.factory.getButton("shooter.cycle_shooter_fixed").onTrue(
            commands2.cmd.runOnce(self.shooter.cycleFixedShootingPosition, self.shooter)
        )

        # Hood input — right trigger analog mapped to hood angle
        self.hood_angle_input = self.factory.getAnalog("hood.angle")

        # Hopper toggle: on/off via left bumper
        hopper_btn = self.factory.getButton("hopper.toggle_hopper")
        hopper_btn.onTrue(
            commands2.cmd.runOnce(lambda: self.hopper.setPower(consts.HopperConstants.defaultPower), self.hopper)
        )
        hopper_btn.onFalse(
            commands2.cmd.runOnce(self.hopper.stop, self.hopper)
        )

        # Intake: toggle deploy/retract (Operator A)
        self.factory.getButton("intake.toggle_deploy").onTrue(
            commands.intake_commands.toggle_intake_deploy(self.intake_position)
        )

        # Ball transport: roller while held (Operator B)
        self.factory.getButton("ball_transport.hold_roller").whileTrue(
            commands.ball_transport.run_roller_while_held(self.intake_roller)
        )

        # Shooter: flywheel spinup toggle (Operator X)
        self.factory.getButton("shooter.spinup_toggle").onTrue(
            commands.shooter_commands.toggle_spinup(self.shooter, self.hood)
        )

        # Ball transport: hopper + feed while held (Driver LT)
        self.factory.getButton("ball_transport.run_hopper_feed").whileTrue(
            commands.ball_transport.run_hopper_and_feed(self.hopper, self.feed)
        )

        # Map all drive axes' scale to a shared SmartDashboard entry.
        # Dashboard changes and Y-button toggles both write to this path;
        # the factory auto-syncs the value into all three analogs each cycle.
        _SPEED_NT = "/SmartDashboard/Drivetrain speed"
        for analog in (self.translate_x, self.translate_y, self.rotate):
            analog.mapParamToNtPath(_SPEED_NT, "scale")

    def _toggle_drive_scale(self) -> None:
        """Toggle between slow and fast drive scale presets.

        Writes the new scale to SmartDashboard; the factory auto-syncs
        it into all three drive analogs via mapParamToNtPath each cycle.
        """
        self._drive_is_slow = not self._drive_is_slow
        scale = self._drive_scale_slow if self._drive_is_slow else self._drive_scale_fast
        wpilib.SmartDashboard.putNumber("Drivetrain speed", scale)

    def getDeployInfo(self, key: str) -> str:
        """Gets the Git SHA of the deployed robot by parsing ~/deploy.json and returning the git-hash from the JSON key OR if deploy.json is unavailable will return "unknown"
            example deploy.json: '{"deploy-host": "DESKTOP-80HA89O", "deploy-user": "ehsra", "deploy-date": "2023-03-02T17:54:14", "code-path": "blah", "git-hash": "3f4e89f138d9d78093bd4869e0cac9b61becd2b9", "git-desc": "3f4e89f-dirty", "git-branch": "fix-recal-nbeasley"}

        Args:
            key (str): The desired json key to get. Popular onces are git-hash, deploy-host, deploy-user

        Returns:
            str: Returns the value of the desired deploy key
        """
        json_object = None
        home = str(Path.home()) + os.path.sep
        release_file = home + 'py' + os.path.sep + "deploy.json"
        try:
            # Read from ~/deploy.json
            with open(release_file, "r") as openfile:
                json_object = json.load(openfile)
                print(json_object)
                print(type(json_object))
                if key in json_object:
                    return json_object[key]
                else:
                    return f"Key: {key} Not Found in JSON"
        except OSError:
            return "unknown"
        except json.JSONDecodeError:
            return "bad json in deploy file check for unescaped "

    def updateAlliance(self) -> None:
        """
        Update the alliance the robot is on
        """
        self.alliance = wpilib.DriverStation.getAlliance()
        self.drivetrain.update_alliance_flag(self.alliance)
