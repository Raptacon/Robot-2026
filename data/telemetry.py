# Internal imports
from config import OperatorRobotConfig
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain
from subsystem.intakeactions import IntakeSubsystem

# Third-party imports
import wpilib
from ntcore import NetworkTableInstance
from wpimath.geometry import Pose2d, Rotation2d
from wpimath.kinematics import ChassisSpeeds, SwerveModuleState
from wpiutil.log import FloatLogEntry, StringLogEntry, BooleanLogEntry

telemetryOdometryEntries = [
    ["robotPose", "robotpose"],
    ["targetPose", "targetpose"],
]

telemetryFullSwerveDriveTrainEntries = [
    ["moduleStates", SwerveModuleState, True, "swervemodeulestates"],
    ["drivetrainVelocity", ChassisSpeeds, False, "swervevelocity"],
    ["drivetrainRotation", Rotation2d, False, "swerverotation"],
]

telemetryRawSwerveDriveTrainEntries = []
for i in range(len(OperatorRobotConfig.swerve_module_channels)):
    telemetryRawSwerveDriveTrainEntries.extend(
        [
            [f"steerDegree{i + 1}", FloatLogEntry, f"module{i + 1}/steerdegree"],
            [f"drivePercent{i + 1}", FloatLogEntry, f"module{i + 1}/drivepercent"],
            [f"moduleVelocity{i + 1}", FloatLogEntry, f"module{i + 1}/velocity"],
        ]
    )

driverStationEntries = [
    ["alliance", StringLogEntry, "alliance"],
    ["autonomous", BooleanLogEntry, "autonomous"],
    ["teleop", BooleanLogEntry, "teleop"],
    ["test", BooleanLogEntry, "test"],
    ["enabled", BooleanLogEntry, "enabled"],
]

intakeEntries = [
    # ["intakeSpeed", "intakespeed"],
    ["rollerSpeed", "rollerspeed"],
]

class Telemetry:

    def __init__(
        self,
        driveTrain: SwerveDrivetrain = None,
        driverStation: wpilib.DriverStation = None,
        intake: IntakeSubsystem = None
    ):
        self.odometryPosition = driveTrain.pose_estimator
        self.driveTrain = driveTrain
        self.swerveModules = driveTrain.swerve_modules
        self.driverStation = driverStation
        self.intake = intake

        self.networkTable = NetworkTableInstance.getDefault()
        for entryname, logname in telemetryOdometryEntries:
            setattr(
                self,
                entryname,
                self.networkTable.getStructTopic(
                    "odometry/" + logname, Pose2d
                ).publish(),
            )
        for (
            entryname,
            entrytype,
            isarraytype,
            logname,
        ) in telemetryFullSwerveDriveTrainEntries:
            if isarraytype:
                setattr(
                    self,
                    entryname,
                    self.networkTable.getStructArrayTopic(
                        "swervedrivetrain/" + logname, entrytype
                    ).publish(),
                )
            else:
                setattr(
                    self,
                    entryname,
                    self.networkTable.getStructTopic(
                        "swervedrivetrain/" + logname, entrytype
                    ).publish(),
                )
        for entryname, logname in intakeEntries:
            setattr(
                self,
                entryname,
                self.networkTable.getStructTopic(
                    "intake/" + logname, entrytype
                ).publish(),
            )

        # DataLogManager is started in robot.py telemInit() — just get the log
        self.datalog = wpilib.DataLogManager.getLog()
        for entryname, entrytype, logname in telemetryRawSwerveDriveTrainEntries:
            setattr(
                self,
                entryname,
                entrytype(self.datalog, "rawswervedrivetrain/" + logname),
            )

    def getOdometryInputs(self):
        """
        Records the data for the positions of the bot in a field,
        Gives the x position, y position and rotation
        """
        if self.odometryPosition is not None:
            pose = self.odometryPosition.getEstimatedPosition()
            self.robotPose.set(pose)

    def getFullSwerveState(self):
        """
        Retrieves values reflecting the current state of the swerve drive
        """
        if self.driveTrain and self.swerveModules:
            self.moduleStates.set(
                [swerveModule.current_state() for swerveModule in self.swerveModules]
            )
            self.drivetrainVelocity.set(self.driveTrain.current_robot_relative_speed())
            self.drivetrainRotation.set(self.driveTrain.current_yaw())

    def getRawSwerveInputs(self):
        """
        Gets the inputs for some swerve drive train inputs
        it get the steer angle, the drive percent and the velocity
        """
        if self.swerveModules is not None:
            for i, swerveModule in enumerate(self.swerveModules):
                getattr(self, f"steerDegree{i + 1}").append(
                    swerveModule.current_raw_absolute_steer_position()
                )
                getattr(self, f"drivePercent{i + 1}").append(
                    swerveModule.drive_motor.getAppliedOutput()
                )
                getattr(self, f"moduleVelocity{i + 1}").append(
                    swerveModule.current_state().speed
                )

    def getDriverStationInputs(self):
        """
        Gets the inputs of some match/general robot things,
        the things being: Alliance color and what mode it is in and
        if it is enabled
        """
        if self.driverStation is not None:
            alliance = "No Alliance"
            if self.driverStation.getAlliance() == wpilib.DriverStation.Alliance.kBlue:
                alliance = "Blue"
            if self.driverStation.getAlliance() == wpilib.DriverStation.Alliance.kRed:
                alliance = "Red"
            self.alliance.append(alliance)
            self.autonomous.append(self.driverStation.isAutonomous())
            self.teleop.append(self.driverStation.isTeleop())
            self.test.append(self.driverStation.isTest())
            self.enabled.append(self.driverStation.isEnabled())


    def getIntakeInputs(self):
        if self.intake is not None:
            # self.intake.intakeVelocity = self.intakeSpeed.getEntry(getattr(self, "intakeSpeed"))
            self.intake.rollerVelocity = self.rollerSpeed.getEntry(getattr(self, "rollerSpeed"))

    def runDefaultDataCollections(self):
        self.getOdometryInputs()
        self.getFullSwerveState()
        self.getRawSwerveInputs()
        self.getIntakeInputs()

    def logAdditionalOdometry(
        self, odometer_value: Pose2d, log_entry_name: str
    ) -> None:
        getattr(self, log_entry_name).set(odometer_value)
