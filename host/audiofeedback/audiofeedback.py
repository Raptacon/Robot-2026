#!/usr/bin/env python3
"""
System tray app that plays sounds when the FRC robot changes mode.

Monitors the Driver Station -> Robot UDP control packets (port 1110) to detect
mode transitions (disabled, teleop, autonomous, test, e-stop) and plays
corresponding sound files.

This requires NO changes to robot code. The DS already sends these packets.

Usage:
    sudo python imdisabled.py [sounds_dir]

    sounds_dir defaults to a "sounds" folder next to this script.
    Place audio files in the sounds directory with these names:
        disabled.mp3    - played when robot transitions to disabled
        teleop.mp3      - played when robot enters teleop
        autonomous.mp3  - played when robot enters autonomous
        test.mp3        - played when robot enters test mode
        estop.mp3       - played when emergency stop is activated

    Missing files are silently skipped — only provide the ones you want.

Requires:
    pip install scapy pystray Pillow
    sudo/admin privileges (packet capture)

macOS:  Uses built-in afplay for audio playback.
Windows: Uses built-in PowerShell for audio playback (install Npcap for capture).
Linux:  Uses mpg123 for audio playback.
"""
import os
import platform
import subprocess
import sys
import threading
import time

try:
    from scapy.all import UDP, sniff
except ImportError:
    print("scapy is required: pip install scapy")
    sys.exit(1)

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("pystray and Pillow are required: pip install pystray Pillow")
    sys.exit(1)

# FRC Driver Station protocol constants
# Source: allwpilib/simulation/halsim_ds_socket/src/main/native/include/DSCommPacket.h
# Packet format (DS -> Robot, UDP port 1110):
#   Bytes 0-1: Sequence number (uint16 big-endian)
#   Byte 2:    Comm version
#   Byte 3:    Control byte (bit flags below)
DS_TO_ROBOT_PORT = 1110
CONTROL_BYTE_OFFSET = 3
MIN_PACKET_LEN = 4

# Control byte bit flags (from DSCommPacket.h)
CONTROL_TEST = 0x01
CONTROL_AUTONOMOUS = 0x02
CONTROL_ENABLED = 0x04
CONTROL_FMS_ATTACHED = 0x08
CONTROL_EMERGENCY_STOP = 0x80

# Cooldown to avoid re-triggering on rapid toggling
COOLDOWN_SECONDS = 3.0

# Robot modes derived from control byte
MODE_DISABLED = "disabled"
MODE_TELEOP = "teleop"
MODE_AUTONOMOUS = "autonomous"
MODE_TEST = "test"
MODE_ESTOP = "estop"

# Tray icon colors for each mode
MODE_COLORS = {
    None: "gray",              # No packets seen yet
    MODE_DISABLED: "red",
    MODE_TELEOP: "green",
    MODE_AUTONOMOUS: "blue",
    MODE_TEST: "yellow",
    MODE_ESTOP: "darkred",
}

# Sound file names expected in the sounds directory
SOUND_FILES = {
    MODE_DISABLED: "disabled.mp3",
    MODE_TELEOP: "teleop.mp3",
    MODE_AUTONOMOUS: "autonomous.mp3",
    MODE_TEST: "test.mp3",
    MODE_ESTOP: "estop.mp3",
}


def decode_mode(control: int) -> str:
    """Decode the control byte into a robot mode string."""
    if control & CONTROL_EMERGENCY_STOP:
        return MODE_ESTOP
    if not (control & CONTROL_ENABLED):
        return MODE_DISABLED
    if control & CONTROL_TEST:
        return MODE_TEST
    if control & CONTROL_AUTONOMOUS:
        return MODE_AUTONOMOUS
    return MODE_TELEOP


def make_icon(color: str) -> Image.Image:
    """Create a simple colored circle icon for the system tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=color, outline="white",
                 width=2)
    return img


def play_sound(path: str) -> None:
    """Play an audio file using platform-native tools."""
    if not path or not os.path.exists(path):
        return
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["afplay", path],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif system == "Windows":
            ps_cmd = (
                f'(New-Object Media.SoundPlayer "{path}").PlaySync()'
            )
            subprocess.Popen(["powershell", "-c", ps_cmd],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["mpg123", "-q", path],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except FileNotFoundError as e:
        print(f"Audio playback failed: {e}")


class DSMonitor:
    """Monitors DS packets, updates the tray icon, and plays sounds."""

    def __init__(self, sounds: dict[str, str | None]):
        self.sounds = sounds
        self.current_mode: str | None = None
        self.last_trigger = 0.0
        self.trigger_count = 0
        self.tray: pystray.Icon | None = None
        self._sniffer_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def process_packet(self, pkt):
        if not pkt.haslayer(UDP):
            return

        payload = bytes(pkt[UDP].payload)
        if len(payload) < MIN_PACKET_LEN:
            return

        control = payload[CONTROL_BYTE_OFFSET]
        mode = decode_mode(control)

        # Update tray icon color
        if self.tray:
            self.tray.icon = make_icon(MODE_COLORS.get(mode, "gray"))

        # Detect mode transition
        if mode != self.current_mode:
            old_mode = self.current_mode
            self.current_mode = mode

            # Skip the initial transition from None (startup)
            if old_mode is None:
                return

            now = time.time()
            if now - self.last_trigger > COOLDOWN_SECONDS:
                self.trigger_count += 1
                sound = self.sounds.get(mode)
                if sound:
                    print(f"Mode: {mode}")
                    play_sound(sound)
                self.last_trigger = now
                self._update_title()

    def _update_title(self):
        if self.tray:
            mode_label = self.current_mode or "unknown"
            self.tray.title = (
                f"Robot: {mode_label} ({self.trigger_count} transition"
                f"{'s' if self.trigger_count != 1 else ''})"
            )

    def _run_sniffer(self):
        try:
            sniff(filter=f"udp dst port {DS_TO_ROBOT_PORT}",
                  prn=self.process_packet,
                  store=0,
                  stop_filter=lambda _: self._stop_event.is_set())
        except PermissionError:
            print("Permission denied - run with sudo/admin privileges.")
            if self.tray:
                self.tray.stop()

    def on_quit(self, icon, item):
        self._stop_event.set()
        icon.stop()

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem("Quit", self.on_quit),
        )

        self.tray = pystray.Icon(
            name="imdisabled",
            icon=make_icon(MODE_COLORS[None]),
            title="Robot Monitor (waiting for packets...)",
            menu=menu,
        )

        self._sniffer_thread = threading.Thread(target=self._run_sniffer,
                                                daemon=True)
        self._sniffer_thread.start()

        # pystray.run() blocks on the main thread (required for macOS)
        self.tray.run()


def load_sounds(sounds_dir: str) -> dict[str, str | None]:
    """Load sound file paths from a directory. Missing files map to None."""
    sounds = {}
    found_any = False
    for mode, filename in SOUND_FILES.items():
        path = os.path.join(sounds_dir, filename)
        if os.path.exists(path):
            sounds[mode] = path
            print(f"  {mode}: {filename}")
            found_any = True
        else:
            sounds[mode] = None
    if not found_any:
        print(f"  (no sound files found in {sounds_dir})")
    return sounds


def main():
    if len(sys.argv) > 1:
        sounds_dir = sys.argv[1]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sounds_dir = os.path.join(script_dir, "sounds")

    print(f"Sounds directory: {sounds_dir}")
    sounds = load_sounds(sounds_dir)

    print(f"\nStarting tray app — monitoring UDP port {DS_TO_ROBOT_PORT}...")

    monitor = DSMonitor(sounds)
    monitor.run()


if __name__ == "__main__":
    main()
