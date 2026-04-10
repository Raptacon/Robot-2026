"""
Publishes DriverStation and robot controller state to NetworkTables
under /RobotState/ so external tools can monitor robot mode without
needing to parse UDP packets or modify other subsystems.
"""
import wpilib
from commands2 import Subsystem
from ntcore.util import ntproperty


class RobotState(Subsystem):
    """Lightweight subsystem that mirrors DriverStation state to NT."""

    nt_enabled = ntproperty("/RobotState/enabled", False, writeDefault=True)
    nt_autonomous = ntproperty("/RobotState/autonomous", False, writeDefault=True)
    nt_teleop = ntproperty("/RobotState/teleop", False, writeDefault=True)
    nt_test = ntproperty("/RobotState/test", False, writeDefault=True)
    nt_estopped = ntproperty("/RobotState/estopped", False, writeDefault=True)
    nt_disabled = ntproperty("/RobotState/disabled", False, writeDefault=True)
    nt_fms_attached = ntproperty("/RobotState/fmsAttached", False, writeDefault=True)
    nt_ds_attached = ntproperty("/RobotState/dsAttached", False, writeDefault=True)
    nt_alliance = ntproperty("/RobotState/alliance", "Unknown", writeDefault=True)
    nt_match_time = ntproperty("/RobotState/matchTime", 0.0, writeDefault=True)
    nt_battery_voltage = ntproperty("/RobotState/batteryVoltage", 0.0, writeDefault=True)
    nt_is_simulation = ntproperty("/RobotState/isSimulation", False, writeDefault=True)
    nt_fms_match_type = ntproperty("/RobotState/fmsMatchType", "None", writeDefault=True)
    nt_fms_match_number = ntproperty("/RobotState/fmsMatchNumber", 0, writeDefault=True)
    nt_fms_event_name = ntproperty("/RobotState/fmsEventName", "", writeDefault=True)
    nt_fms_replay_number = ntproperty("/RobotState/fmsReplayNumber", 0, writeDefault=True)
    nt_station_location = ntproperty("/RobotState/stationLocation", 0, writeDefault=True)

    def periodic(self) -> None:
        self.nt_enabled = wpilib.DriverStation.isEnabled()
        self.nt_autonomous = wpilib.DriverStation.isAutonomous()
        self.nt_teleop = wpilib.DriverStation.isTeleop()
        self.nt_test = wpilib.DriverStation.isTest()
        self.nt_estopped = wpilib.DriverStation.isEStopped()
        self.nt_disabled = wpilib.DriverStation.isDisabled()
        self.nt_fms_attached = wpilib.DriverStation.isFMSAttached()
        self.nt_ds_attached = wpilib.DriverStation.isDSAttached()
        self.nt_match_time = wpilib.DriverStation.getMatchTime()
        self.nt_battery_voltage = wpilib.RobotController.getBatteryVoltage()
        self.nt_is_simulation = wpilib.RobotBase.isSimulation()

        alliance = wpilib.DriverStation.getAlliance()
        if alliance == wpilib.DriverStation.Alliance.kRed:
            self.nt_alliance = "Red"
        elif alliance == wpilib.DriverStation.Alliance.kBlue:
            self.nt_alliance = "Blue"
        else:
            self.nt_alliance = "Unknown"

        # FMS info
        self.nt_fms_event_name = wpilib.DriverStation.getEventName()
        self.nt_fms_match_number = wpilib.DriverStation.getMatchNumber()
        self.nt_fms_replay_number = wpilib.DriverStation.getReplayNumber()
        self.nt_station_location = wpilib.DriverStation.getLocation() or 0

        match_type = wpilib.DriverStation.getMatchType()
        if match_type == wpilib.DriverStation.MatchType.kPractice:
            self.nt_fms_match_type = "Practice"
        elif match_type == wpilib.DriverStation.MatchType.kQualification:
            self.nt_fms_match_type = "Qualification"
        elif match_type == wpilib.DriverStation.MatchType.kElimination:
            self.nt_fms_match_type = "Elimination"
        else:
            self.nt_fms_match_type = "None"
