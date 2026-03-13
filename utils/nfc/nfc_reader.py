"""PN532 NFC reader protocol layer.

Implements ISO14443A tag detection and NTAG page reading on top of a
duck-typed transport (anything with write_command/read_response/is_open).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# PN532 command codes
_CMD_SAM_CONFIG = 0x14
_CMD_IN_LIST_PASSIVE_TARGET = 0x4A
_CMD_IN_DATA_EXCHANGE = 0x40

# ISO14443A baud rate code
_MIFARE_ISO14443A = 0x00

# NTAG READ command (reads 4 pages = 16 bytes at a time)
_NTAG_CMD_READ = 0x30

# Response codes
_RESP_SAM_CONFIG = 0x15
_RESP_IN_LIST_PASSIVE_TARGET = 0x4B
_RESP_IN_DATA_EXCHANGE = 0x41


def parse_ndef_text_records(data: bytes) -> list:
    """Parse NDEF text records from NTAG user data pages.

    NTAG user data starts with a TLV block:
      - 0x03 = NDEF Message TLV, followed by length, then NDEF records
      - 0xFE = Terminator TLV

    Each NDEF record has:
      - Header byte (MB, ME, CF, SR, IL, TNF)
      - Type length, payload length (1 or 4 bytes if SR), optional ID length
      - Type, optional ID, payload

    For Text records (TNF=0x01, type="T"):
      - Payload[0] = status byte (bit 7 = encoding, bits 5-0 = lang code length)
      - Payload[1:1+lang_len] = language code (e.g. "en")
      - Payload[1+lang_len:] = the actual text

    Returns a list of decoded text strings.
    """
    texts = []
    if not data or len(data) < 3:
        return texts

    # Find NDEF Message TLV (type 0x03)
    pos = 0
    while pos < len(data):
        tlv_type = data[pos]
        if tlv_type == 0x00:
            # NULL TLV, skip
            pos += 1
            continue
        if tlv_type == 0xFE:
            # Terminator
            break
        if pos + 1 >= len(data):
            break
        tlv_len = data[pos + 1]
        pos += 2
        if tlv_len == 0xFF:
            # 3-byte length format
            if pos + 2 > len(data):
                break
            tlv_len = (data[pos] << 8) | data[pos + 1]
            pos += 2

        if tlv_type == 0x03:
            # NDEF Message — parse records within
            ndef_data = data[pos:pos + tlv_len]
            texts.extend(_parse_ndef_records(ndef_data))

        pos += tlv_len

    return texts


def _parse_ndef_records(data: bytes) -> list:
    """Parse NDEF records from an NDEF message payload."""
    texts = []
    pos = 0
    while pos < len(data):
        if pos >= len(data):
            break
        header = data[pos]
        pos += 1
        tnf = header & 0x07
        sr = bool(header & 0x10)  # Short Record
        il = bool(header & 0x08)  # ID Length present

        if pos >= len(data):
            break
        type_len = data[pos]
        pos += 1

        if sr:
            if pos >= len(data):
                break
            payload_len = data[pos]
            pos += 1
        else:
            if pos + 4 > len(data):
                break
            payload_len = int.from_bytes(data[pos:pos + 4], 'big')
            pos += 4

        id_len = 0
        if il:
            if pos >= len(data):
                break
            id_len = data[pos]
            pos += 1

        rec_type = data[pos:pos + type_len]
        pos += type_len
        pos += id_len  # skip ID
        payload = data[pos:pos + payload_len]
        pos += payload_len

        # TNF 0x01 = Well-Known, type "T" = Text
        if tnf == 0x01 and rec_type == b'T' and len(payload) >= 1:
            status = payload[0]
            lang_len = status & 0x3F
            encoding = 'utf-8' if (status & 0x80) == 0 else 'utf-16'
            if len(payload) > 1 + lang_len:
                text = payload[1 + lang_len:].decode(encoding, errors='replace')
                texts.append(text)

    return texts


class NfcTagData:
    """Data read from an NFC tag."""

    def __init__(self, uid: bytes, user_data: bytes = b""):
        self.uid = uid
        self.user_data = user_data

    @property
    def uid_hex(self) -> str:
        return self.uid.hex().upper()

    def get_text_records(self) -> list:
        """Parse NDEF text records from user data.

        Returns a list of text strings found in NDEF Text records.
        """
        return parse_ndef_text_records(self.user_data)

    def get_text(self) -> str:
        """Get all NDEF text records joined, or raw decode as fallback."""
        records = self.get_text_records()
        if records:
            return ' | '.join(records)
        # Fallback: raw decode
        try:
            return self.user_data.rstrip(b'\x00').decode('utf-8', errors='replace')
        except Exception:
            return ""

    def __repr__(self):
        return f"NfcTagData(uid={self.uid_hex}, data_len={len(self.user_data)})"


class NfcReader:
    """PN532 NFC reader using a duck-typed transport.

    The transport must implement:
        - is_open: bool property
        - write_command(data: bytes) -> bool
        - read_response() -> Optional[bytes]
    """

    def __init__(self, transport):
        self._transport = transport
        self._initialized = False

    @property
    def is_ready(self) -> bool:
        return self._transport.is_open and self._initialized

    def begin(self) -> bool:
        """Initialize the PN532 with SAMConfig (normal mode).

        Returns True if the PN532 responded correctly.
        """
        if not self._transport.is_open:
            return False

        # SAMConfig: normal mode (0x01), timeout 0, no IRQ
        if not self._transport.write_command(bytes([_CMD_SAM_CONFIG, 0x01, 0x00, 0x00])):
            logger.warning("NFC SAMConfig: no ACK")
            return False

        resp = self._transport.read_response()
        if resp is None or len(resp) < 1 or resp[0] != _RESP_SAM_CONFIG:
            logger.warning("NFC SAMConfig: bad response")
            return False

        self._initialized = True
        logger.info("NFC reader initialized")
        return True

    def read_passive_target(self) -> Optional[tuple]:
        """Poll for an ISO14443A tag and return (target_num, uid), or None.

        Returns a tuple of (target_number, uid_bytes) where target_number
        is needed for subsequent InDataExchange commands.
        """
        if not self.is_ready:
            return None

        # InListPassiveTarget: 1 target, ISO14443A
        cmd = bytes([_CMD_IN_LIST_PASSIVE_TARGET, 0x01, _MIFARE_ISO14443A])
        if not self._transport.write_command(cmd):
            return None

        resp = self._transport.read_response()
        if resp is None or len(resp) < 2:
            return None

        if resp[0] != _RESP_IN_LIST_PASSIVE_TARGET:
            return None

        num_targets = resp[1]
        if num_targets == 0:
            return None

        # Parse target data: [tg, sens_res(2), sel_res, nfcid_len, nfcid...]
        if len(resp) < 7:
            return None

        tg = resp[2]  # target number assigned by PN532
        nfcid_len = resp[6]
        if len(resp) < 7 + nfcid_len:
            return None

        uid = bytes(resp[7:7 + nfcid_len])
        logger.debug("NFC target %d detected, UID: %s", tg, uid.hex().upper())
        return (tg, uid)

    def read_ntag_pages(self, tg: int, start_page: int,
                        num_pages: int) -> Optional[bytes]:
        """Read NTAG user data pages.

        Each NTAG READ command returns 4 pages (16 bytes). This method
        issues multiple reads to cover the requested page range.

        Args:
            tg: Target number from read_passive_target().
            start_page: First page number to read (NTAG pages are 4 bytes each).
            num_pages: Number of pages to read.

        Returns:
            Concatenated page data, or None on failure.
        """
        if not self.is_ready:
            return None

        result = bytearray()
        page = start_page
        remaining = num_pages

        while remaining > 0:
            data = self._read_4_pages(tg, page)
            if data is None:
                return None

            # Each read returns 16 bytes (4 pages). Take only what we need.
            pages_in_read = min(4, remaining)
            result.extend(data[:pages_in_read * 4])
            page += 4
            remaining -= pages_in_read

        return bytes(result)

    def read_full_tag(self, user_data_start: int = 4,
                      user_data_pages: int = 36) -> Optional[NfcTagData]:
        """Read a tag's UID and user data in one operation.

        The UID detection and page reads use the same target listing so
        the tag must remain on the reader for the entire operation.

        Args:
            user_data_start: First user data page (default 4 for NTAG21x).
            user_data_pages: Number of user data pages to read (default 36
                for NTAG213; use 128 for NTAG215, 226 for NTAG216).

        Returns:
            NfcTagData with UID and user data, or None on failure.
        """
        result = self.read_passive_target()
        if result is None:
            return None

        tg, uid = result
        user_data = self.read_ntag_pages(tg, user_data_start, user_data_pages)
        if user_data is None:
            # Tag detected but read failed — caller may want to retry
            logger.debug("NFC tag %s listed but page read failed", uid.hex().upper())
            return NfcTagData(uid=uid, user_data=b"")

        return NfcTagData(uid=uid, user_data=user_data)

    def _read_4_pages(self, tg: int, page: int) -> Optional[bytes]:
        """Issue a single NTAG READ for 4 pages (16 bytes) starting at page."""
        # InDataExchange: target number, NTAG/Ultralight READ cmd, page address
        cmd = bytes([_CMD_IN_DATA_EXCHANGE, tg & 0xFF, _NTAG_CMD_READ, page & 0xFF])
        if not self._transport.write_command(cmd):
            logger.debug("NFC page read: no ACK for page %d", page)
            return None

        resp = self._transport.read_response()
        if resp is None or len(resp) < 2:
            logger.debug("NFC page read: no/short response for page %d (got %s)",
                         page, resp.hex(' ') if resp else 'None')
            return None

        logger.debug("NFC page %d raw response (%d bytes): %s",
                     page, len(resp), resp.hex(' '))

        if resp[0] != _RESP_IN_DATA_EXCHANGE:
            logger.debug("NFC page read: unexpected response code 0x%02X", resp[0])
            return None

        # First byte after command code is status (0x00 = success)
        status = resp[1]
        if status != 0x00:
            logger.debug("NFC page read error at page %d: status 0x%02X", page, status)
            return None

        # Remaining bytes are the 16 bytes of page data
        if len(resp) < 18:  # 1 cmd + 1 status + 16 data
            logger.debug("NFC page read: short response (%d bytes) for page %d",
                         len(resp), page)
            return None

        return bytes(resp[2:18])
