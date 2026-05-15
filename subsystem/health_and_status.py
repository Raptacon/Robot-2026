import os
import wpilib
import commands2
from ntcore import NetworkTableInstance
from ntcore.util import ntproperty

# Network interface used for DS/radio comms on the roboRIO
_NET_IFACE = "eth0"

_B = "/subsystems/HealthAndStatus"


class HealthAndStatus(commands2.SubsystemBase):
    """
    Publishes Power Distribution Panel, RobotController, Driver Station,
    and Linux OS health data to NetworkTables under subsystems/HealthAndStatus/.
    DataLogManager.logNetworkTables(True) in robot.py captures all entries to
    the wpilog automatically.

    Linux metrics (CPU, memory, network) are read from /proc and are skipped
    gracefully in simulation.

    NT entry updateRateSec controls how often data is published (0 = every loop).
    """

    # Operator-adjustable update rate; 0 = update every periodic call (~50 Hz)
    updateRateSec = ntproperty(f"{_B}/updateRateSec", 0.0,
                               writeDefault=False, persistent=True)

    # -- PDP --
    pdp_voltage = ntproperty(f"{_B}/pdp/voltage", 0.0)
    pdp_total_current = ntproperty(f"{_B}/pdp/totalCurrent", 0.0)
    pdp_temperature = ntproperty(f"{_B}/pdp/temperature", 0.0)
    pdp_has_sticky_faults = ntproperty(f"{_B}/pdp/hasStickyFaults", False)

    # -- RobotController --
    rc_battery_voltage = ntproperty(f"{_B}/robotcontroller/batteryVoltage", 0.0)
    rc_brownout_voltage = ntproperty(f"{_B}/robotcontroller/brownoutVoltage", 0.0)
    rc_input_voltage = ntproperty(f"{_B}/robotcontroller/inputVoltage", 0.0)
    rc_input_current = ntproperty(f"{_B}/robotcontroller/inputCurrent", 0.0)
    rc_browned_out = ntproperty(f"{_B}/robotcontroller/brownedOut", False)
    rc_sys_active = ntproperty(f"{_B}/robotcontroller/systemActive", False)
    rc_cpu_temp = ntproperty(f"{_B}/robotcontroller/cpuTemp", 0.0)
    rc_comms_disable_count = ntproperty(f"{_B}/robotcontroller/commsDisableCount", 0)
    rc_radio_state = ntproperty(f"{_B}/robotcontroller/radioState", "")
    rc_can_utilization = ntproperty(f"{_B}/robotcontroller/canUtilization", 0.0)
    rc_can_bus_off = ntproperty(f"{_B}/robotcontroller/canBusOffCount", 0)
    rc_can_tx_errors = ntproperty(f"{_B}/robotcontroller/canTxErrors", 0)
    rc_can_rx_errors = ntproperty(f"{_B}/robotcontroller/canRxErrors", 0)
    rc_can_tx_full = ntproperty(f"{_B}/robotcontroller/canTxFullCount", 0)
    rc_3v3_voltage = ntproperty(f"{_B}/robotcontroller/rail3v3/voltage", 0.0)
    rc_3v3_current = ntproperty(f"{_B}/robotcontroller/rail3v3/current", 0.0)
    rc_3v3_active = ntproperty(f"{_B}/robotcontroller/rail3v3/active", False)
    rc_3v3_faults = ntproperty(f"{_B}/robotcontroller/rail3v3/faultCount", 0)
    rc_5v_voltage = ntproperty(f"{_B}/robotcontroller/rail5v/voltage", 0.0)
    rc_5v_current = ntproperty(f"{_B}/robotcontroller/rail5v/current", 0.0)
    rc_5v_active = ntproperty(f"{_B}/robotcontroller/rail5v/active", False)
    rc_5v_faults = ntproperty(f"{_B}/robotcontroller/rail5v/faultCount", 0)
    rc_6v_voltage = ntproperty(f"{_B}/robotcontroller/rail6v/voltage", 0.0)
    rc_6v_current = ntproperty(f"{_B}/robotcontroller/rail6v/current", 0.0)
    rc_6v_active = ntproperty(f"{_B}/robotcontroller/rail6v/active", False)
    rc_6v_faults = ntproperty(f"{_B}/robotcontroller/rail6v/faultCount", 0)

    # -- Driver Station --
    ds_alliance = ntproperty(f"{_B}/driverstation/alliance", "")
    ds_station = ntproperty(f"{_B}/driverstation/station", "")
    ds_enabled = ntproperty(f"{_B}/driverstation/enabled", False)
    ds_autonomous = ntproperty(f"{_B}/driverstation/autonomous", False)
    ds_teleop = ntproperty(f"{_B}/driverstation/teleop", False)
    ds_test = ntproperty(f"{_B}/driverstation/test", False)
    ds_fms_attached = ntproperty(f"{_B}/driverstation/fmsAttached", False)
    ds_ds_attached = ntproperty(f"{_B}/driverstation/dsAttached", False)
    ds_match_time = ntproperty(f"{_B}/driverstation/matchTime", 0.0)
    ds_match_number = ntproperty(f"{_B}/driverstation/matchNumber", 0)
    ds_event_name = ntproperty(f"{_B}/driverstation/eventName", "")

    # -- Linux OS metrics (roboRIO only, skipped in sim) --
    sys_cpu_pct = ntproperty(f"{_B}/system/cpuPercent", 0.0)
    sys_load_1 = ntproperty(f"{_B}/system/loadAvg1m", 0.0)
    sys_load_5 = ntproperty(f"{_B}/system/loadAvg5m", 0.0)
    sys_load_15 = ntproperty(f"{_B}/system/loadAvg15m", 0.0)
    sys_mem_total_mb = ntproperty(f"{_B}/system/memTotalMB", 0.0)
    sys_mem_used_mb = ntproperty(f"{_B}/system/memUsedMB", 0.0)
    sys_mem_free_mb = ntproperty(f"{_B}/system/memFreeMB", 0.0)
    sys_mem_pct = ntproperty(f"{_B}/system/memPercent", 0.0)
    net_rx_packets = ntproperty(f"{_B}/system/network/rxPackets", 0)
    net_tx_packets = ntproperty(f"{_B}/system/network/txPackets", 0)
    net_rx_errors = ntproperty(f"{_B}/system/network/rxErrors", 0)
    net_tx_errors = ntproperty(f"{_B}/system/network/txErrors", 0)
    net_rx_dropped = ntproperty(f"{_B}/system/network/rxDropped", 0)
    net_tx_dropped = ntproperty(f"{_B}/system/network/txDropped", 0)
    net_rx_kbps = ntproperty(f"{_B}/system/network/rxKbps", 0.0)
    net_tx_kbps = ntproperty(f"{_B}/system/network/txKbps", 0.0)

    def __init__(self):
        super().__init__()
        import logging
        self._log = logging.getLogger(__name__)

        self._is_sim = wpilib.RobotBase.isSimulation()
        self._last_update: float = 0.0

        # PDP may not be present (e.g. bench testing without CAN bus)
        try:
            self.pdp = wpilib.PowerDistribution()
            self._has_pdp = True
        except Exception as e:
            self._log.warning("No PDP/PDH found, PDP telemetry disabled: %s", e)
            self.pdp = None
            self._has_pdp = False

        # State for CPU % calculation between calls
        self._prev_cpu_idle: int = 0
        self._prev_cpu_total: int = 0

        # State for bandwidth calculation between calls
        self._prev_net_rx_bytes: int = 0
        self._prev_net_tx_bytes: int = 0
        self._prev_net_time: float = wpilib.Timer.getFPGATimestamp()

        # PDP per-channel currents — dynamic count, use publishers directly
        self._pdp_channels = []
        if self._has_pdp:
            nt = NetworkTableInstance.getDefault()
            pdp_table = nt.getTable("subsystems/HealthAndStatus/pdp")
            self._pdp_channels = [
                pdp_table.getFloatTopic(f"channel{i}").publish()
                for i in range(self.pdp.getNumChannels())
            ]

    def periodic(self):
        now = wpilib.Timer.getFPGATimestamp()
        rate = self.updateRateSec
        if rate > 0.0 and (now - self._last_update) < rate:
            return
        self._last_update = now
        self._log_pdp()
        self._log_robot_controller()
        self._log_driver_station()
        if not self._is_sim:
            self._log_system_metrics()

    def _log_pdp(self):
        if not self._has_pdp:
            return
        try:
            self.pdp_voltage = self.pdp.getVoltage()
            self.pdp_total_current = self.pdp.getTotalCurrent()
            self.pdp_temperature = self.pdp.getTemperature()
            sf = self.pdp.getStickyFaults()
            self.pdp_has_sticky_faults = any([
                sf.Brownout, sf.CanBusOff, sf.CanWarning,
                sf.HardwareFault, sf.FirmwareFault, sf.HasReset,
            ])
            for i, entry in enumerate(self._pdp_channels):
                entry.set(self.pdp.getCurrent(i))
        except Exception as e:
            self._log.warning("PDP read failed, disabling PDP telemetry: %s", e)
            self._has_pdp = False

    def _log_robot_controller(self):
        rc = wpilib.RobotController
        self.rc_battery_voltage = rc.getBatteryVoltage()
        self.rc_brownout_voltage = rc.getBrownoutVoltage()
        self.rc_input_voltage = rc.getInputVoltage()
        self.rc_input_current = rc.getInputCurrent()
        self.rc_browned_out = rc.isBrownedOut()
        self.rc_sys_active = rc.isSysActive()
        self.rc_cpu_temp = rc.getCPUTemp()
        self.rc_comms_disable_count = rc.getCommsDisableCount()

        radio = rc.getRadioLEDState()
        radio_names = {
            wpilib.RadioLEDState.kOff: "Off",
            wpilib.RadioLEDState.kGreen: "Green",
            wpilib.RadioLEDState.kRed: "Red",
            wpilib.RadioLEDState.kOrange: "Orange",
        }
        self.rc_radio_state = radio_names.get(radio, "Unknown")

        can = rc.getCANStatus()
        self.rc_can_utilization = can.percentBusUtilization
        self.rc_can_bus_off = can.busOffCount
        self.rc_can_tx_errors = can.transmitErrorCount
        self.rc_can_rx_errors = can.receiveErrorCount
        self.rc_can_tx_full = can.txFullCount

        self.rc_3v3_voltage = rc.getVoltage3V3()
        self.rc_3v3_current = rc.getCurrent3V3()
        self.rc_3v3_active = rc.getEnabled3V3()
        self.rc_3v3_faults = rc.getFaultCount3V3()

        self.rc_5v_voltage = rc.getVoltage5V()
        self.rc_5v_current = rc.getCurrent5V()
        self.rc_5v_active = rc.getEnabled5V()
        self.rc_5v_faults = rc.getFaultCount5V()

        self.rc_6v_voltage = rc.getVoltage6V()
        self.rc_6v_current = rc.getCurrent6V()
        self.rc_6v_active = rc.getEnabled6V()
        self.rc_6v_faults = rc.getFaultCount6V()

    def _log_driver_station(self):
        ds = wpilib.DriverStation

        ally = ds.getAlliance()
        if ally == wpilib.DriverStation.Alliance.kBlue:
            alliance = "Blue"
        elif ally == wpilib.DriverStation.Alliance.kRed:
            alliance = "Red"
        else:
            alliance = "None"
        self.ds_alliance = alliance

        location = ds.getLocation()
        self.ds_station = f"{alliance}{location}" if location else alliance

        self.ds_enabled = ds.isEnabled()
        self.ds_autonomous = ds.isAutonomous()
        self.ds_teleop = ds.isTeleop()
        self.ds_test = ds.isTest()
        self.ds_fms_attached = ds.isFMSAttached()
        self.ds_ds_attached = ds.isDSAttached()
        self.ds_match_time = ds.getMatchTime()
        self.ds_match_number = ds.getMatchNumber()
        self.ds_event_name = ds.getEventName()

    def _log_system_metrics(self):
        self._log_cpu()
        self._log_memory()
        self._log_network()

    def _log_cpu(self):
        # Load averages: 1 / 5 / 15 min (Unix only)
        load1, load5, load15 = os.getloadavg()
        self.sys_load_1 = load1
        self.sys_load_5 = load5
        self.sys_load_15 = load15

        # Instantaneous CPU % via /proc/stat delta
        try:
            with open("/proc/stat") as f:
                fields = f.readline().split()
            # fields: cpu user nice system idle iowait irq softirq steal guest guest_nice
            vals = [int(x) for x in fields[1:]]
            idle = vals[3]
            total = sum(vals)
            d_idle = idle - self._prev_cpu_idle
            d_total = total - self._prev_cpu_total
            if d_total > 0:
                self.sys_cpu_pct = 100.0 * (1.0 - d_idle / d_total)
            self._prev_cpu_idle = idle
            self._prev_cpu_total = total
        except OSError:
            pass  # /proc/stat not available on Windows/sim — expected

    def _log_memory(self):
        try:
            mem = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    key, val = line.split(":", 1)
                    mem[key.strip()] = int(val.split()[0])  # kB
            total_mb = mem.get("MemTotal", 0) / 1024.0
            avail_mb = mem.get("MemAvailable", 0) / 1024.0
            used_mb = total_mb - avail_mb
            self.sys_mem_total_mb = total_mb
            self.sys_mem_used_mb = used_mb
            self.sys_mem_free_mb = avail_mb
            if total_mb > 0:
                self.sys_mem_pct = 100.0 * used_mb / total_mb
        except OSError:
            pass  # /proc/meminfo not available on Windows/sim — expected

    def _log_network(self):
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    if _NET_IFACE + ":" in line:
                        parts = line.split()
                        # /proc/net/dev columns after iface:
                        # rx: bytes packets errs drop fifo frame compressed multicast
                        # tx: bytes packets errs drop fifo colls carrier compressed
                        rx_bytes = int(parts[1])
                        tx_bytes = int(parts[9])
                        self.net_rx_packets = int(parts[2])
                        self.net_rx_errors = int(parts[3])
                        self.net_rx_dropped = int(parts[4])
                        self.net_tx_packets = int(parts[10])
                        self.net_tx_errors = int(parts[11])
                        self.net_tx_dropped = int(parts[12])

                        now = wpilib.Timer.getFPGATimestamp()
                        dt = now - self._prev_net_time
                        if dt > 0 and self._prev_net_rx_bytes > 0:
                            self.net_rx_kbps = (rx_bytes - self._prev_net_rx_bytes) / dt / 1024.0
                            self.net_tx_kbps = (tx_bytes - self._prev_net_tx_bytes) / dt / 1024.0
                        self._prev_net_rx_bytes = rx_bytes
                        self._prev_net_tx_bytes = tx_bytes
                        self._prev_net_time = now
                        break
        except OSError:
            pass  # /proc/net/dev not available on Windows/sim — expected
