# Native imports
import json
import os
from pathlib import Path
from typing import Callable

# Internal imports
from data.telemetry import Telemetry
from constants import PoseOptions, MechConsts
from vision import Vision
from commands.auto.pathplan_to_pose import pathplanToPose
from commands.default_swerve_drive import DefaultDrive
import commands.operate_elevator as elevCommands
import commands.operate_intake as IntakeCommands
from commands.operate_elevator import ElevateManually
from lookups.utils import getCurrentReefZone
from lookups.reef_positions import reef_position_lookup
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from subsystem.captainIntake import CaptainIntake

# Third-party imports
import commands2
import ntcore
import wpilib
import wpimath
import wpinet
from commands2.button import Trigger
from pathplannerlib.auto import AutoBuilder
from subsystem.diverCarlElevator import DiverCarlElevator as Elevator
from subsystem.diverCarlChistera import DiverCarlChistera as Arm

class RobotSwerve:
    """
    Container to hold the main robot code
    """
    # forward declare critical types for editors
    drivetrain: SwerveDrivetrain
    elevator: Elevator
    arm: Arm

    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        # networktables setup
        self.inst = ntcore.NetworkTableInstance.getDefault()
        self.table = self.inst.getTable("Stream_Deck")
        self.field = wpilib.Field2d()
        wpilib.SmartDashboard.putData("Field", self.field)

        # Subsystem instantiation
        self.drivetrain = SwerveDrivetrain()
        self.elevator = Elevator()
        self.arm = Arm()
        # cross link arm and elevator
        self.arm.setElevator(self.elevator)
        self.elevator.setArm(self.arm)
        self.alliance = "red" if self.drivetrain.flip_to_red_alliance() else "blue"

        self.intake_subsystem = CaptainIntake()

        # Vision setup
        try:
            self.vision = Vision(self.drivetrain)
        except Exception:
            self.vision = None
            wpilib.reportError("Unable to load vision class", printTrace=True)
        self.alignmentTagId = None
        self.caughtPeriodicVisionError = False

        # Initialize timer
        self.timer = wpilib.Timer()
        self.timer.start()

        # Elastic Setup
        wpinet.WebServer.getInstance().start(5800, wpilib.getDeployDirectory())

        # HID setup
        wpilib.DriverStation.silenceJoystickConnectionWarning(True)
        self.driver_controller = wpilib.XboxController(0)
        self.mech_controller = wpilib.XboxController(1)

        # Auto Setup
        self.auto_command = None
        self.auto_chooser = AutoBuilder.buildAutoChooser()

        wpilib.SmartDashboard.putData("Select auto routine", self.auto_chooser)

        # Telemetry setup
        self.enableTelemetry = wpilib.SmartDashboard.getBoolean("enableTelemetry", True)
        if self.enableTelemetry:
            self.telemetry = Telemetry(
                driveTrain=self.drivetrain, elevator=self.elevator, vision=self.vision, intake=self.intake_subsystem
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
        if self.enableTelemetry and self.telemetry:
            self.telemetry.runDefaultDataCollections()

        self.field.setRobotPose(self.drivetrain.current_pose())

        if self.vision is not None:
            try:
                self.vision.getCamEstimates(specificTagId=lambda: self.alignmentTagId)
                self.vision.showTargetData()
            except Exception:
                if not self.caughtPeriodicVisionError:
                    self.caughtPeriodicVisionError = True
                    wpilib.reportError("Retrieval of vision info failed in periodic", printTrace=True)

    def disabledInit(self):
        self.drivetrain.set_motor_stop_modes(to_drive=True, to_break=True, all_motor_override=True, burn_flash=False)
        self.drivetrain.stop_driving()

        self.elevator.motor.set(0)

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        self.auto_command = self.auto_chooser.getSelected()
        if self.auto_command:
            self.auto_command.schedule()
        else:
            self.drivetrain.reset_pose_estimator(self.drivetrain.get_default_starting_pose())

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        self.table.putNumber("pressedKey", -1)
        self.keys = {0: commands2.cmd.print_("Key 0 pressed"),
                     1: commands2.cmd.print_("Key 1 pressed"),
                     2: commands2.cmd.print_("Key 2 pressed"),
                     3: commands2.cmd.print_("Key 3 pressed"),
                     4: commands2.cmd.print_("Key 4 pressed"),
                     5: commands2.cmd.print_("Key 5 pressed"),
                     6: commands2.cmd.print_("Key 6 pressed"),
                     7: commands2.cmd.print_("Key 7 pressed"),
                     8: commands2.cmd.print_("Key 8 pressed"),
                     9: commands2.cmd.print_("Key 9 pressed"),
                     10: commands2.cmd.print_("Key 10 pressed"),
                     11: commands2.cmd.print_("Key 11 pressed"),
                     12: commands2.cmd.print_("Key 12 pressed"),
                     13: commands2.cmd.print_("Key 13 pressed"),
                     14: commands2.cmd.print_("Key 14 pressed"),
                     -1: commands2.cmd.print_("No key pressed"),}

        if self.auto_command:
            self.auto_command.cancel()

        self.alliance = "blue"
        if self.drivetrain.flip_to_red_alliance():
            self.alliance = "red"
        self.teleop_auto_command = None

        self.drivetrain.setDefaultCommand(
            DefaultDrive(
                self.drivetrain,
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getLeftY(), 0.06),
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getLeftX(), 0.06),
                lambda: wpimath.applyDeadband(-1 * self.driver_controller.getRightX(), 0.1),
                lambda: not self.driver_controller.getRightBumperButton(),
                lambda: self.driver_controller.getLeftBumperButton(),
                lambda: self.driver_controller.getRightTriggerAxis() > 0.5
            )
        )

        self.teleop_auto_triggers = {
            "left_reef_align": Trigger(self.driver_controller.getXButtonPressed).onTrue(
                commands2.cmd.parallel(
                    commands2.InstantCommand(
                        lambda: self.setAlignmentTag(
                            reef_position_lookup
                            .get(
                                (self.alliance, getCurrentReefZone(self.alliance, self.drivetrain.current_pose), "l"),
                                {}
                            )
                            .get("tag", None)
                        )
                    ),
                    commands2.DeferredCommand(
                        lambda: pathplanToPose(lambda: reef_position_lookup.get(
                            (self.alliance, getCurrentReefZone(self.alliance, self.drivetrain.current_pose), "l"),
                            {}
                        ).get("pose", None)
                        )
                    )
                ).finallyDo(lambda interrupted: self.setAlignmentTag(None))
            ),
             "right_reef_align": Trigger(self.driver_controller.getBButtonPressed).onTrue(
                commands2.cmd.parallel(
                    commands2.InstantCommand(
                        lambda: self.setAlignmentTag(
                            reef_position_lookup
                            .get(
                                (self.alliance, getCurrentReefZone(self.alliance, self.drivetrain.current_pose), "r"),
                                {}
                            )
                            .get("tag", None)
                        )
                    ),
                    commands2.DeferredCommand(lambda: pathplanToPose(lambda: reef_position_lookup.get(
                        (self.alliance, getCurrentReefZone(self.alliance, self.drivetrain.current_pose), "r"),
                        {}
                    ).get("pose", None)))
                ).finallyDo(lambda interrupted: self.setAlignmentTag(None))
             ),
        }

        self.elevator.setDefaultCommand(ElevateManually(
            self.elevator,
            self.arm,
            lambda: (
                wpimath.applyDeadband(self.mech_controller.getLeftY(), 0.2)
            )
        ))
        # Allow manual override of elevator movement by operator, even if a setpoint command is active
        Trigger(lambda: abs(wpimath.applyDeadband(self.mech_controller.getLeftY(), 0.2)) > 0).whileTrue(
            ElevateManually(
                self.elevator,
                self.arm,
                lambda: (
                    wpimath.applyDeadband(self.mech_controller.getLeftY(), 0.2)
                )
            )
        )

        self.intake_subsystem.setDefaultCommand(IntakeCommands.IntakeManually(
            lambda: int(self.mech_controller.getRightBumperButton()),
            self.intake_subsystem
        ))
        # Allow manual override of intake movement by operator, even if moving based on breakbeams
        Trigger(lambda: self.mech_controller.getRightTriggerAxis() > 0.1).whileTrue(
            IntakeCommands.IntakeManually(
                lambda: wpimath.applyDeadband(-1 * self.mech_controller.getRightTriggerAxis(), 0.1),
                self.intake_subsystem
            )
        )
        Trigger(lambda: self.mech_controller.getRightBumperButton()).whileTrue(
            IntakeCommands.IntakeManually(lambda: 1, self.intake_subsystem)
        )


        Trigger(self.mech_controller.getYButtonPressed).onTrue(
            elevCommands.genPivotElevatorCommand(self.arm, self.elevator, PoseOptions.REEF4)
        )
        Trigger(self.mech_controller.getBButtonPressed).onTrue(
            elevCommands.genPivotElevatorCommand(self.arm, self.elevator, PoseOptions.REEF3)
        )
        Trigger(self.mech_controller.getAButtonPressed).onTrue(
            elevCommands.genPivotElevatorCommand(self.arm, self.elevator, PoseOptions.REEF2)
        )
        Trigger(self.mech_controller.getXButtonPressed).onTrue(
            elevCommands.genPivotElevatorCommand(self.arm, self.elevator, PoseOptions.TROUGH)
        )
        Trigger(self.mech_controller.getLeftBumperButtonPressed).onTrue(
            elevCommands.genPivotElevatorCommand(self.arm, self.elevator, PoseOptions.REST)
        )

        Trigger(lambda: wpimath.applyDeadband(self.mech_controller.getRightY(), 0.06) > 0).whileTrue(
            elevCommands.PivotManually(self.arm, lambda: -1 * self.mech_controller.getRightY() * MechConsts.kArmAngleIncrement)
        )

    def teleopPeriodic(self):
        if self.driver_controller.getLeftTriggerAxis() > 0.5:
            commands2.CommandScheduler.getInstance().cancelAll()
        self.keyPressed = self.table.getNumber("pressedKey", -1)
        self.heartbeat = self.table.getNumber("Stream Deck Heartbeat", 0)
        wpilib.SmartDashboard.putNumber("Stream Deck Life", self.heartbeat)

        wpilib.SmartDashboard.putBoolean("A Button Pressed", self.mech_controller.getRightBumperButton())

    def testInit(self):
        commands2.CommandScheduler.getInstance().cancelAll()

    def testPeriodic(self):
        pass

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
        releaseFile = home + 'py' + os.path.sep + "deploy.json"
        try:
            # Read from ~/deploy.json
            with open(releaseFile, "r") as openfile:
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

    def isArmSafe(self) -> bool:
        """
        """
        return True

    def setAlignmentTag(self, alignmentTagId: int | None) -> None:
        """
        """
        self.alignmentTagId = alignmentTagId
