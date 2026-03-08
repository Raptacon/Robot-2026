import os
import wpilib
import commands2
from ntcore import NetworkTableInstance
from ntcore.util import ntproperty

# Network interface used for DS/radio comms on the roboRIO
_NET_IFACE = "eth0"

_NT_BASE = "subsystems/HealthAndStatus"


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
    updateRateSec = ntproperty(
        f"/{_NT_BASE}/updateRateSec", 0.0,
        writeDefault=False, persistent=True,
    )

    def __init__(self):
        super().__init__()

        self._is_sim = wpilib.RobotBase.isSimulation()
        self._last_update: float = 0.0

        self.pdp = wpilib.PowerDistribution()
        nt = NetworkTableInstance.getDefault()

        # State for CPU % calculation between calls
        self._prev_cpu_idle: int = 0
        self._prev_cpu_total: int = 0

        # State for bandwidth calculation between calls
        self._prev_net_rx_bytes: int = 0
        self._prev_net_tx_bytes: int = 0
        self._prev_net_time: float = wpilib.Timer.getFPGATimestamp()

        # -- PDP --
        pdp_table = nt.getTable(f"{_NT_BASE}/pdp")
        self._pdp_voltage = pdp_table.getFloatTopic("voltage").publish()
        self._pdp_total_current = pdp_table.getFloatTopic("totalCurrent").publish()
        self._pdp_temperature = pdp_table.getFloatTopic("temperature").publish()
        self._pdp_sticky_faults = pdp_table.getIntegerTopic("stickyFaults").publish()
        self._pdp_channels = [
            pdp_table.getFloatTopic(f"channel{i}").publish()
            for i in range(self.pdp.getNumChannels())
        ]

        # -- RobotController --
        rc_table = nt.getTable(f"{_NT_BASE}/robotcontroller")
        self._rc_battery_voltage = rc_table.getFloatTopic("batteryVoltage").publish()
        self._rc_brownout_voltage = rc_table.getFloatTopic("brownoutVoltage").publish()
        self._rc_input_voltage = rc_table.getFloatTopic("inputVoltage").publish()
        self._rc_input_current = rc_table.getFloatTopic("inputCurrent").publish()
        self._rc_browned_out = rc_table.getBooleanTopic("brownedOut").publish()
        self._rc_sys_active = rc_table.getBooleanTopic("systemActive").publish()
        self._rc_cpu_temp = rc_table.getFloatTopic("cpuTemp").publish()
        self._rc_comms_disable_count = rc_table.getIntegerTopic("commsDisableCount").publish()
        self._rc_radio_state = rc_table.getStringTopic("radioState").publish()
        self._rc_can_utilization = rc_table.getFloatTopic("canUtilization").publish()
        self._rc_can_bus_off = rc_table.getIntegerTopic("canBusOffCount").publish()
        self._rc_can_tx_errors = rc_table.getIntegerTopic("canTxErrors").publish()
        self._rc_can_rx_errors = rc_table.getIntegerTopic("canRxErrors").publish()
        self._rc_can_tx_full = rc_table.getIntegerTopic("canTxFullCount").publish()
        rail_3v3 = rc_table.getSubTable("rail3v3")
        self._rc_3v3_voltage = rail_3v3.getFloatTopic("voltage").publish()
        self._rc_3v3_current = rail_3v3.getFloatTopic("current").publish()
        self._rc_3v3_active = rail_3v3.getBooleanTopic("active").publish()
        self._rc_3v3_faults = rail_3v3.getIntegerTopic("faultCount").publish()
        rail_5v = rc_table.getSubTable("rail5v")
        self._rc_5v_voltage = rail_5v.getFloatTopic("voltage").publish()
        self._rc_5v_current = rail_5v.getFloatTopic("current").publish()
        self._rc_5v_active = rail_5v.getBooleanTopic("active").publish()
        self._rc_5v_faults = rail_5v.getIntegerTopic("faultCount").publish()
        rail_6v = rc_table.getSubTable("rail6v")
        self._rc_6v_voltage = rail_6v.getFloatTopic("voltage").publish()
        self._rc_6v_current = rail_6v.getFloatTopic("current").publish()
        self._rc_6v_active = rail_6v.getBooleanTopic("active").publish()
        self._rc_6v_faults = rail_6v.getIntegerTopic("faultCount").publish()

        # -- Driver Station --
        ds_table = nt.getTable(f"{_NT_BASE}/driverstation")
        self._ds_alliance = ds_table.getStringTopic("alliance").publish()
        self._ds_station = ds_table.getStringTopic("station").publish()
        self._ds_enabled = ds_table.getBooleanTopic("enabled").publish()
        self._ds_autonomous = ds_table.getBooleanTopic("autonomous").publish()
        self._ds_teleop = ds_table.getBooleanTopic("teleop").publish()
        self._ds_test = ds_table.getBooleanTopic("test").publish()
        self._ds_fms_attached = ds_table.getBooleanTopic("fmsAttached").publish()
        self._ds_ds_attached = ds_table.getBooleanTopic("dsAttached").publish()
        self._ds_match_time = ds_table.getFloatTopic("matchTime").publish()
        self._ds_match_number = ds_table.getIntegerTopic("matchNumber").publish()
        self._ds_event_name = ds_table.getStringTopic("eventName").publish()

        # -- Linux OS metrics (roboRIO only, skipped in sim) --
        sys_table = nt.getTable(f"{_NT_BASE}/system")
        self._sys_cpu_pct = sys_table.getFloatTopic("cpuPercent").publish()
        self._sys_load_1 = sys_table.getFloatTopic("loadAvg1m").publish()
        self._sys_load_5 = sys_table.getFloatTopic("loadAvg5m").publish()
        self._sys_load_15 = sys_table.getFloatTopic("loadAvg15m").publish()
        self._sys_mem_total_mb = sys_table.getFloatTopic("memTotalMB").publish()
        self._sys_mem_used_mb = sys_table.getFloatTopic("memUsedMB").publish()
        self._sys_mem_free_mb = sys_table.getFloatTopic("memFreeMB").publish()
        self._sys_mem_pct = sys_table.getFloatTopic("memPercent").publish()
        net_table = sys_table.getSubTable("network")
        self._net_rx_packets = net_table.getIntegerTopic("rxPackets").publish()
        self._net_tx_packets = net_table.getIntegerTopic("txPackets").publish()
        self._net_rx_errors = net_table.getIntegerTopic("rxErrors").publish()
        self._net_tx_errors = net_table.getIntegerTopic("txErrors").publish()
        self._net_rx_dropped = net_table.getIntegerTopic("rxDropped").publish()
        self._net_tx_dropped = net_table.getIntegerTopic("txDropped").publish()
        self._net_rx_kbps = net_table.getFloatTopic("rxKbps").publish()
        self._net_tx_kbps = net_table.getFloatTopic("txKbps").publish()

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
        self._pdp_voltage.set(self.pdp.getVoltage())
        self._pdp_total_current.set(self.pdp.getTotalCurrent())
        self._pdp_temperature.set(self.pdp.getTemperature())
        self._pdp_sticky_faults.set(self.pdp.getStickyFaults().value)
        for i, entry in enumerate(self._pdp_channels):
            entry.set(self.pdp.getCurrent(i))

    def _log_robot_controller(self):
        rc = wpilib.RobotController
        self._rc_battery_voltage.set(rc.getBatteryVoltage())
        self._rc_brownout_voltage.set(rc.getBrownoutVoltage())
        self._rc_input_voltage.set(rc.getInputVoltage())
        self._rc_input_current.set(rc.getInputCurrent())
        self._rc_browned_out.set(rc.isBrownedOut())
        self._rc_sys_active.set(rc.isSysActive())
        self._rc_cpu_temp.set(rc.getCPUTemp())
        self._rc_comms_disable_count.set(rc.getCommsDisableCount())

        radio = rc.getRadioLEDState()
        radio_names = {
            wpilib.RobotController.RadioLEDState.kOff: "Off",
            wpilib.RobotController.RadioLEDState.kGreen: "Green",
            wpilib.RobotController.RadioLEDState.kRed: "Red",
            wpilib.RobotController.RadioLEDState.kOrange: "Orange",
        }
        self._rc_radio_state.set(radio_names.get(radio, "Unknown"))

        can = rc.getCANStatus()
        self._rc_can_utilization.set(can.percentBusUtilization)
        self._rc_can_bus_off.set(can.busOffCount)
        self._rc_can_tx_errors.set(can.transmitErrorCount)
        self._rc_can_rx_errors.set(can.receiveErrorCount)
        self._rc_can_tx_full.set(can.txFullCount)

        self._rc_3v3_voltage.set(rc.getVoltage3V3())
        self._rc_3v3_current.set(rc.getCurrent3V3())
        self._rc_3v3_active.set(rc.getEnabled3V3())
        self._rc_3v3_faults.set(rc.getFaultCount3V3())

        self._rc_5v_voltage.set(rc.getVoltage5V())
        self._rc_5v_current.set(rc.getCurrent5V())
        self._rc_5v_active.set(rc.getEnabled5V())
        self._rc_5v_faults.set(rc.getFaultCount5V())

        self._rc_6v_voltage.set(rc.getVoltage6V())
        self._rc_6v_current.set(rc.getCurrent6V())
        self._rc_6v_active.set(rc.getEnabled6V())
        self._rc_6v_faults.set(rc.getFaultCount6V())

    def _log_driver_station(self):
        ds = wpilib.DriverStation

        ally = ds.getAlliance()
        if ally == wpilib.DriverStation.Alliance.kBlue:
            alliance = "Blue"
        elif ally == wpilib.DriverStation.Alliance.kRed:
            alliance = "Red"
        else:
            alliance = "None"
        self._ds_alliance.set(alliance)

        location = ds.getLocation()
        self._ds_station.set(f"{alliance}{location}" if location else alliance)

        self._ds_enabled.set(ds.isEnabled())
        self._ds_autonomous.set(ds.isAutonomous())
        self._ds_teleop.set(ds.isTeleop())
        self._ds_test.set(ds.isTest())
        self._ds_fms_attached.set(ds.isFMSAttached())
        self._ds_ds_attached.set(ds.isDSAttached())
        self._ds_match_time.set(ds.getMatchTime())
        self._ds_match_number.set(ds.getMatchNumber())
        self._ds_event_name.set(ds.getEventName())

    def _log_system_metrics(self):
        self._log_cpu()
        self._log_memory()
        self._log_network()

    def _log_cpu(self):
        # Load averages: 1 / 5 / 15 min (Unix only)
        load1, load5, load15 = os.getloadavg()
        self._sys_load_1.set(load1)
        self._sys_load_5.set(load5)
        self._sys_load_15.set(load15)

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
                self._sys_cpu_pct.set(100.0 * (1.0 - d_idle / d_total))
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
            self._sys_mem_total_mb.set(total_mb)
            self._sys_mem_used_mb.set(used_mb)
            self._sys_mem_free_mb.set(avail_mb)
            if total_mb > 0:
                self._sys_mem_pct.set(100.0 * used_mb / total_mb)
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
                        self._net_rx_packets.set(int(parts[2]))
                        self._net_rx_errors.set(int(parts[3]))
                        self._net_rx_dropped.set(int(parts[4]))
                        self._net_tx_packets.set(int(parts[10]))
                        self._net_tx_errors.set(int(parts[11]))
                        self._net_tx_dropped.set(int(parts[12]))

                        now = wpilib.Timer.getFPGATimestamp()
                        dt = now - self._prev_net_time
                        if dt > 0 and self._prev_net_rx_bytes > 0:
                            self._net_rx_kbps.set((rx_bytes - self._prev_net_rx_bytes) / dt / 1024.0)
                            self._net_tx_kbps.set((tx_bytes - self._prev_net_tx_bytes) / dt / 1024.0)
                        self._prev_net_rx_bytes = rx_bytes
                        self._prev_net_tx_bytes = tx_bytes
                        self._prev_net_time = now
                        break
        except OSError:
            pass  # /proc/net/dev not available on Windows/sim — expected
