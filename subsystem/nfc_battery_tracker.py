"""NFC Battery Tracker subsystem.

Reads an NTAG tag attached to the robot battery via a PN532 NFC reader
connected over UART. Publishes the battery serial number and UID to
NetworkTables for match logging and driver warnings.

Polling strategy:
- When disabled and no valid data yet: poll at a configurable interval (~1s).
- On read error where a tag IS detected but data read fails: retry immediately.
- Once a full successful read yields valid battery data: stop polling.
- If a different tag UID appears: log it and update.
- On disabledInit: reset and resume polling (battery may have changed on power cycle).
- When enabled (teleop/auto): do NOT poll.
"""

import logging
import time

import commands2
import wpilib
from ntcore import NetworkTableType
from ntcore.util import ntproperty

from config import NfcBatteryTrackerConfig as Cfg
from utils.nfc import NfcReader, NfcSerialTransport, NfcTagData

logger = logging.getLogger(__name__)


class NfcBatteryTracker(commands2.Subsystem):
    """Subsystem that identifies the installed battery via NFC."""

    battery_sn = ntproperty('/NfcBatteryTracker/batterySN', 'unknown',
                            writeDefault=True)
    battery_year = ntproperty('/NfcBatteryTracker/batteryYear', '',
                              writeDefault=True)
    battery_note = ntproperty('/NfcBatteryTracker/batteryNote', '',
                              writeDefault=True)
    battery_uri = ntproperty('/NfcBatteryTracker/batteryURI', '',
                             writeDefault=True)
    uid = ntproperty('/NfcBatteryTracker/uid', '',
                     writeDefault=True)
    status = ntproperty('/NfcBatteryTracker/status', 'initializing',
                        writeDefault=True)
    tag_data = ntproperty('/NfcBatteryTracker/tagData', [],
                          writeDefault=True,
                          type=NetworkTableType.kStringArray)

    def __init__(self):
        super().__init__()
        self.setName("NfcBatteryTracker")

        self._transport = NfcSerialTransport(
            port=Cfg.nfc_serial_port,
            baudrate=Cfg.nfc_baud_rate,
        )
        self._reader = NfcReader(self._transport)

        # State
        self._current_uid: str = ""
        self._has_valid_data = False
        self._retry_read = False  # True when tag detected but data read failed
        self._retry_count: int = 0
        _MAX_RETRIES = 5
        self._max_retries = _MAX_RETRIES
        self._last_poll_time: float = 0.0
        self._reader_ok = False

        # Attempt initial connection
        self._init_reader()

    def _init_reader(self):
        """Try to open transport and initialize the PN532."""
        if self._transport.open():
            if self._reader.begin():
                self._reader_ok = True
                self.status = "ready"
                logger.info("NFC battery tracker ready on %s", Cfg.nfc_serial_port)
            else:
                self.status = "init_failed"
                logger.warning("NFC PN532 init failed — reader not responding")
                self._transport.close()
        else:
            self.status = "no_reader"
            logger.warning(
                "NFC serial port %s not available — battery tracking disabled",
                Cfg.nfc_serial_port,
            )

    def periodic(self):
        """Called every 20ms by the scheduler."""
        if not self._reader_ok:
            return

        # Don't poll when enabled (battery can't change mid-match)
        if wpilib.DriverStation.isEnabled():
            return

        # Check if it's time to poll
        now = time.monotonic()
        if self._retry_read:
            # Retry immediately on partial read failure
            self._retry_read = False
        elif self._has_valid_data:
            # Already have good data — no need to poll
            return
        else:
            # Throttle polling to configured interval
            if (now - self._last_poll_time) < Cfg.nfc_poll_interval_disabled:
                return

        self._last_poll_time = now
        self._poll_tag()

    def _poll_tag(self):
        """Attempt to read a tag and update state."""
        tag_data = self._reader.read_full_tag()

        if tag_data is None:
            # No tag present
            self.status = "no_tag"
            return

        uid_hex = tag_data.uid_hex

        # Tag detected but user data read failed — schedule retry with limit
        if len(tag_data.user_data) == 0:
            self._retry_count += 1
            if self._retry_count <= self._max_retries:
                self.status = "read_error"
                self._retry_read = True
                logger.warning(
                    "NFC tag detected (UID: %s) but data read failed, "
                    "retry %d/%d", uid_hex, self._retry_count, self._max_retries
                )
            else:
                self.status = "read_failed"
                self._retry_read = False
                logger.error(
                    "NFC tag (UID: %s) data read failed after %d retries, "
                    "will retry next poll interval",
                    uid_hex, self._max_retries,
                )
                self._retry_count = 0
            return

        # Check if this is a new/different tag
        if uid_hex == self._current_uid and self._has_valid_data:
            # Same tag, already logged — nothing to do
            return

        # Successful full read — reset retry counter
        self._retry_count = 0

        # Log all tag details
        self._current_uid = uid_hex
        self._log_tag_data(tag_data)

        # Extract battery data from tag text
        text = tag_data.get_text()
        uri = tag_data.get_uri()
        self.uid = uid_hex
        self.battery_uri = uri

        # Publish all key=value pairs as string array
        self._publish_tag_data(text, uri)

        if text and self._looks_like_battery(text):
            fields = self._parse_battery_fields(text)
            self.battery_sn = fields.get('sn', '')
            self.battery_year = fields.get('year', '')
            self.battery_note = fields.get('note', '')
            self._has_valid_data = True
            self.status = "ok"
            logger.info("Battery identified — SN: %s (UID: %s)",
                        self.battery_sn, uid_hex)
        else:
            self.battery_sn = f"unrecognized (UID: {uid_hex})"
            self.battery_year = ''
            self.battery_note = ''
            self._has_valid_data = False
            self.status = "unrecognized_tag"
            logger.warning(
                "NFC tag UID %s does not contain valid battery data",
                uid_hex)

    def _log_tag_data(self, tag_data: NfcTagData):
        """Log all tag details including non-zero data pages."""
        logger.info("NFC tag read — UID: %s", tag_data.uid_hex)
        logger.info("NFC tag text: %r", tag_data.get_text())

        # Log non-zero data in hex for debugging
        data = tag_data.user_data
        if data:
            # Log in 16-byte (4-page) chunks, skip all-zero chunks
            for offset in range(0, len(data), 16):
                chunk = data[offset:offset + 16]
                if any(b != 0 for b in chunk):
                    page_num = 4 + (offset // 4)  # user data starts at page 4
                    logger.info(
                        "NFC pages %d-%d: %s",
                        page_num, page_num + 3,
                        chunk.hex(' '),
                    )

    def _looks_like_battery(self, text: str) -> bool:
        """Check if tag text looks like valid battery data.

        Format: bat: section header with sn=XXX key-value line.
        """
        return 'bat:' in text and 'sn=' in text

    def _parse_battery_fields(self, text: str) -> dict:
        """Extract all key=value fields from bat: section."""
        fields = {}
        if 'bat:' in text:
            section = text.split('bat:', 1)[1]
            for line in section.split('\n'):
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    fields[k.strip()] = v.strip()
        return fields

    def _publish_tag_data(self, text: str, uri: str):
        """Publish all tag data as a string array to NT."""
        data = []
        if uri:
            data.append(f"uri={uri}")
        if text:
            for line in text.strip().split('\n'):
                line = line.strip()
                if line:
                    data.append(line)
        self.tag_data = data

    def onDisabledInit(self):
        """Called when robot transitions to disabled.

        Reset polling state so we re-scan for the battery.
        The battery may have been swapped during a power cycle.
        """
        self._has_valid_data = False
        self._retry_read = False
        self._retry_count = 0
        self._current_uid = ""
        self.battery_sn = "unknown"
        self.battery_year = ""
        self.battery_note = ""
        self.battery_uri = ""
        self.uid = ""
        self.tag_data = []
        self.status = "scanning" if self._reader_ok else self.status
        logger.info("NFC battery tracker reset — scanning for battery")

    def close(self):
        """Clean up serial port."""
        self._transport.close()
