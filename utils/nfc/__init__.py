"""NFC utilities for PN532 tag reading/writing over UART (HSU protocol)."""

from utils.nfc.nfc_reader import NfcReader, NfcTagData  # noqa: F401
from utils.nfc.nfc_reader import parse_ndef_text_records, parse_ndef_uri_records  # noqa: F401,E501
from utils.nfc.nfc_serial_transport import NfcSerialTransport  # noqa: F401
from utils.nfc.nfc_writer import build_battery_ndef, encode_ndef_text_record  # noqa: F401,E501
from utils.nfc.nfc_writer import encode_ndef_uri_record, wrap_ndef_message  # noqa: F401,E501

__all__ = [
    "NfcReader", "NfcTagData", "NfcSerialTransport",
    "parse_ndef_text_records", "parse_ndef_uri_records",
    "build_battery_ndef", "encode_ndef_text_record",
    "encode_ndef_uri_record", "wrap_ndef_message",
]
