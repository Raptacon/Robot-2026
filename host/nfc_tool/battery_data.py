"""Battery data model for NFC tags.

Data is stored on tags as a single NDEF Text record with an INI-style
section header ('bat:') followed by key=value lines.
"""

from dataclasses import dataclass


@dataclass
class BatteryData:
    """Parsed battery information from an NFC tag."""
    sn: str = ''
    year: str = ''
    note: str = ''

    @classmethod
    def from_text(cls, text):
        """Parse bat: section with key=value lines.

        Tolerant of unknown keys and missing bat: prefix.
        """
        if 'bat:' in text:
            text = text.split('bat:', 1)[1]
        fields = {}
        for line in text.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                fields[k.strip()] = v.strip()
        return cls(
            sn=fields.get('sn', ''),
            year=fields.get('year', ''),
            note=fields.get('note', ''),
        )

    def to_text(self):
        """Serialize to bat: section format for NDEF Text record."""
        lines = [f"bat:", f"sn={self.sn}", f"year={self.year}"]
        if self.note:
            lines.append(f"note={self.note}")
        return '\n'.join(lines)

    def is_valid(self):
        """Battery data is valid if it has a serial number."""
        return bool(self.sn.strip())

    def is_battery_tag(self):
        """Check if text was recognized as battery data."""
        return bool(self.sn)
