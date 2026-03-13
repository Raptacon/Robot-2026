"""Quick standalone PN532 debug script — test tag detection and page reads."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logging
logging.basicConfig(level=logging.DEBUG)

from utils.nfc.nfc_serial_transport import NfcSerialTransport
from utils.nfc.nfc_reader import NfcReader

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM12'

transport = NfcSerialTransport(PORT, timeout=1.0)
if not transport.open():
    print(f"Failed to open {PORT}")
    sys.exit(1)

reader = NfcReader(transport)
if not reader.begin():
    print("PN532 init failed")
    sys.exit(1)

print("Waiting for tag...")
tag = reader.read_full_tag(user_data_start=4, user_data_pages=40)
if tag is None:
    print("No tag found")
    transport.close()
    sys.exit(0)

print(f"UID: {tag.uid_hex} ({len(tag.uid)} bytes)")
print(f"User data ({len(tag.user_data)} bytes): {tag.user_data.hex(' ')}")
print(f"\nNDEF text records: {tag.get_text_records()}")
print(f"Combined text: {tag.get_text()}")

# Log non-zero pages
print("\n--- Non-zero data pages ---")
data = tag.user_data
for offset in range(0, len(data), 16):
    chunk = data[offset:offset + 16]
    if any(b != 0 for b in chunk):
        page_num = 4 + (offset // 4)
        ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"  Pages {page_num:3d}-{page_num+3:3d}: {chunk.hex(' ')}  |  {ascii_repr}")

transport.close()
