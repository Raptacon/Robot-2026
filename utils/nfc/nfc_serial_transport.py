"""PySerial-based transport for PN532 HSU (UART) communication.

Handles the PN532 wire format: preamble, length, TFI, data, checksums.
Designed as a duck-typed transport so a future wpilib.SerialPort adapter
can swap in without changing the reader layer.
"""

import logging
import serial

logger = logging.getLogger(__name__)

# PN532 HSU frame constants
_PREAMBLE = bytes([0x00, 0x00, 0xFF])
_POSTAMBLE = bytes([0x00])
_ACK = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])
_TFI_HOST_TO_PN532 = 0xD4
_TFI_PN532_TO_HOST = 0xD5
# Wake-up sequence: 0x55 repeated then preamble
_WAKEUP = bytes([0x55] * 24)


class NfcSerialTransport:
    """Low-level serial transport for PN532 using HSU (UART) protocol."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.05):
        self._port_name = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial: serial.Serial | None = None

    def open(self) -> bool:
        """Open the serial port and wake the PN532.

        Returns True on success, False on failure.
        """
        try:
            self._serial = serial.Serial(
                self._port_name,
                baudrate=self._baudrate,
                timeout=self._timeout,
            )
            self._wake()
            logger.info("NFC transport opened on %s", self._port_name)
            return True
        except serial.SerialException as e:
            logger.warning("Failed to open NFC serial port %s: %s", self._port_name, e)
            self._serial = None
            return False

    def close(self):
        """Close the serial port."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            self._serial = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def write_command(self, command_data: bytes) -> bool:
        """Send a command frame to the PN532.

        Args:
            command_data: Command bytes (TFI 0xD4 is prepended automatically).

        Returns True if the PN532 ACKed the frame.
        """
        if not self.is_open:
            return False

        frame = self._build_frame(command_data)
        try:
            self._serial.reset_input_buffer()
            self._serial.write(frame)
            return self._read_ack()
        except serial.SerialException as e:
            logger.warning("NFC write error: %s", e)
            return False

    def read_response(self) -> bytes | None:
        """Read a response frame from the PN532.

        Returns the response data (after TFI byte) or None on error/timeout.
        """
        if not self.is_open:
            return None

        try:
            # Find preamble
            if not self._wait_for_preamble():
                return None

            # Read length and length checksum
            header = self._serial.read(2)
            if len(header) < 2:
                return None

            length = header[0]
            lcs = header[1]
            if (length + lcs) & 0xFF != 0:
                logger.debug("NFC bad length checksum")
                return None

            # Read TFI + data + DCS + postamble
            payload = self._serial.read(length + 2)
            if len(payload) < length + 2:
                return None

            tfi_and_data = payload[:length]
            dcs = payload[length]

            # Verify data checksum
            if (sum(tfi_and_data) + dcs) & 0xFF != 0:
                logger.debug("NFC bad data checksum")
                return None

            # Verify TFI is PN532-to-host
            if tfi_and_data[0] != _TFI_PN532_TO_HOST:
                logger.debug("NFC unexpected TFI: 0x%02X", tfi_and_data[0])
                return None

            # Return data after TFI
            return bytes(tfi_and_data[1:])
        except serial.SerialException as e:
            logger.warning("NFC read error: %s", e)
            return None

    def _build_frame(self, command_data: bytes) -> bytes:
        """Build a complete PN532 HSU frame with TFI=0xD4."""
        data_with_tfi = bytes([_TFI_HOST_TO_PN532]) + command_data
        length = len(data_with_tfi)
        lcs = (~length + 1) & 0xFF
        dcs = (~sum(data_with_tfi) + 1) & 0xFF
        return _PREAMBLE + bytes([length, lcs]) + data_with_tfi + bytes([dcs]) + _POSTAMBLE

    def _wake(self):
        """Send wake-up sequence to PN532."""
        if self._serial:
            self._serial.write(_WAKEUP)
            self._serial.flush()
            # Discard any garbage after wake
            self._serial.reset_input_buffer()

    def _read_ack(self) -> bool:
        """Read and verify ACK frame."""
        ack = self._serial.read(len(_ACK))
        return ack == _ACK

    def _wait_for_preamble(self) -> bool:
        """Scan incoming bytes until preamble (00 00 FF) is found."""
        # Read up to 100 bytes looking for preamble
        consecutive_zeros = 0
        for _ in range(100):
            b = self._serial.read(1)
            if len(b) == 0:
                return False
            if b[0] == 0x00:
                consecutive_zeros += 1
            elif b[0] == 0xFF and consecutive_zeros >= 2:
                return True
            else:
                consecutive_zeros = 0
        return False
