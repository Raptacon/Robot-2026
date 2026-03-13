"""NDEF message encoding for writing to NTAG tags.

Builds NDEF records (URI and Text) and wraps them in TLV format
ready to write to NTAG user data pages starting at page 4.
"""

# NDEF URI identifier codes — common prefixes compressed to 1 byte.
# Order matters: longer prefixes must come first so the first match
# is the most specific (e.g. 'http://www.' before 'http://').
_URI_PREFIX_MAP = {
    'http://www.': 0x01,
    'https://www.': 0x02,
    'http://': 0x03,
    'https://': 0x04,
    'tel:': 0x05,
    'mailto:': 0x06,
}

# Maximum user data bytes on NTAG variants
NTAG213_MAX_BYTES = 144   # pages 4-39,  36 pages
NTAG215_MAX_BYTES = 504   # pages 4-129, 126 pages
NTAG216_MAX_BYTES = 888   # pages 4-225, 222 pages


def encode_ndef_uri_record(uri, first=False, last=False):
    """Encode a single NDEF URI record (Well-Known type 'U').

    Args:
        uri: Full URI string (e.g. 'http://www.raptacon.org').
        first: Set MB (Message Begin) flag.
        last: Set ME (Message End) flag.

    Returns:
        bytes of the encoded NDEF record (without TLV wrapper).
    """
    # Find longest matching prefix
    prefix_code = 0x00
    uri_body = uri
    for prefix, code in _URI_PREFIX_MAP.items():
        if uri.startswith(prefix):
            prefix_code = code
            uri_body = uri[len(prefix):]
            break

    payload = bytes([prefix_code]) + uri_body.encode('utf-8')

    # Header: TNF=0x01 (Well-Known), SR=1 (short record)
    header = 0x11  # SR | TNF=0x01
    if first:
        header |= 0x80  # MB
    if last:
        header |= 0x40  # ME

    # type = 'U', type_len = 1
    return bytes([header, 0x01, len(payload), ord('U')]) + payload


def encode_ndef_text_record(text, lang='en', first=False, last=False):
    """Encode a single NDEF Text record (Well-Known type 'T').

    Args:
        text: The text content.
        lang: Language code (default 'en').
        first: Set MB (Message Begin) flag.
        last: Set ME (Message End) flag.

    Returns:
        bytes of the encoded NDEF record (without TLV wrapper).
    """
    lang_bytes = lang.encode('ascii')
    text_bytes = text.encode('utf-8')
    # Status byte: bit 7 = 0 (UTF-8), bits 5-0 = lang code length
    status_byte = len(lang_bytes) & 0x3F
    payload = bytes([status_byte]) + lang_bytes + text_bytes

    # Header: TNF=0x01 (Well-Known), SR=1 (short record)
    header = 0x11  # SR | TNF=0x01
    if first:
        header |= 0x80  # MB
    if last:
        header |= 0x40  # ME

    if len(payload) > 255:
        # Long record (SR=0, 4-byte payload length)
        header &= ~0x10  # clear SR bit
        hdr = bytes([header, 0x01]) + len(payload).to_bytes(4, 'big')
        return hdr + b'T' + payload

    # type = 'T', type_len = 1
    return bytes([header, 0x01, len(payload), ord('T')]) + payload


def wrap_ndef_message(records):
    """Wrap concatenated NDEF records in an NDEF Message TLV.

    Args:
        records: list of bytes, each an encoded NDEF record.

    Returns:
        bytes with TLV header (0x03, length) + records + terminator (0xFE).
    """
    msg = b''.join(records)
    msg_len = len(msg)

    if msg_len < 0xFF:
        tlv = bytes([0x03, msg_len]) + msg
    else:
        # 3-byte length format
        tlv = bytes([0x03, 0xFF,
                     (msg_len >> 8) & 0xFF,
                     msg_len & 0xFF]) + msg

    # Append terminator TLV
    return tlv + bytes([0xFE])


def build_battery_ndef(sn, year, note='',
                       uri='http://www.raptacon.org',
                       max_bytes=NTAG215_MAX_BYTES):
    """Build a complete NDEF message for a battery tag.

    Creates two records:
      1. URI record (for phone scanning / lost item recovery)
      2. Text record with bat: section and key=value data

    Args:
        sn: Battery serial number.
        year: Battery year.
        note: Optional note.
        uri: URI for the first record (default team website).
        max_bytes: Maximum tag capacity in bytes.

    Returns:
        bytes ready to write starting at NTAG page 4.

    Raises:
        ValueError: If the NDEF message exceeds tag capacity.
    """
    records = []

    has_uri = bool(uri)

    # Record 1: URI (MB=1, ME=0 if text follows)
    if has_uri:
        records.append(
            encode_ndef_uri_record(uri, first=True, last=False)
        )

    # Record 2: Text with bat: section (MB depends on URI, ME=1)
    text = f"bat:\nsn={sn}\nyear={year}"
    if note:
        text += f"\nnote={note}"
    records.append(
        encode_ndef_text_record(text, first=not has_uri, last=True)
    )

    data = wrap_ndef_message(records)

    if len(data) > max_bytes:
        raise ValueError(
            f"NDEF message ({len(data)} bytes) exceeds tag capacity "
            f"({max_bytes} bytes)")

    return data
