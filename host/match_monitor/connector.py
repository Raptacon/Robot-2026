"""Host-side TCP connector that polls for the roboRIO and maintains a control channel."""

import json
import logging
import socket
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("match_monitor")

CONTROL_PORT = 5805
ROBOT_ADDRESSES = ['roboRIO-3200-FRC.local', '172.22.11.2']
POLL_INTERVAL = 10  # seconds between connection attempts
KEEPALIVE_INTERVAL = 10  # seconds between PINGs
KEEPALIVE_TIMEOUT = 30  # seconds to wait for PONG


class RobotConnector:
    """Polls for the roboRIO, opens a TCP control channel, and handles keepalive.

    When the robot sends UPLOAD_COMPLETE, triggers .wpilog analysis via the
    provided callback.
    """

    def __init__(self, http_port: int, on_upload_complete=None) -> None:
        self._http_port = http_port
        self._on_upload_complete = on_upload_complete
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the connector thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _poll_loop(self) -> None:
        """Poll for the roboRIO and connect when found."""
        logger.info(f"Polling for roboRIO on port {CONTROL_PORT} "
                    f"(addresses: {', '.join(ROBOT_ADDRESSES)})")

        while not self._stop_event.is_set():
            for addr in ROBOT_ADDRESSES:
                if self._stop_event.is_set():
                    return
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)
                    sock.connect((addr, CONTROL_PORT))
                    logger.info(f"Connected to robot at {addr}:{CONTROL_PORT}")
                    self._handle_connection(sock, addr)
                    logger.info(f"Disconnected from robot at {addr}, resuming polling")
                except (socket.timeout, ConnectionRefusedError, OSError):
                    pass
                except Exception:
                    logger.exception(f"Error connecting to {addr}")

            # Wait before next poll cycle
            self._stop_event.wait(POLL_INTERVAL)

    def _handle_connection(self, sock: socket.socket, robot_addr: str) -> None:
        """Run handshake and keepalive loop on an established connection."""
        try:
            # Send HELLO
            hello = json.dumps({
                'type': 'HELLO',
                'http_port': self._http_port,
            }) + '\n'
            sock.sendall(hello.encode('utf-8'))

            # Wait for HELLO_ACK
            sock.settimeout(10)
            buf = ''
            buf = self._read_message(sock, buf)
            if buf is None:
                return
            msg, buf = self._parse_next_message(buf)
            if msg is None or msg.get('type') != 'HELLO_ACK':
                logger.warning(f"Expected HELLO_ACK, got: {msg}")
                return

            logger.info(f"Handshake complete with {robot_addr}")

            # Keepalive + message loop
            last_ping = time.monotonic()
            sock.settimeout(1.0)  # short timeout for non-blocking reads

            while not self._stop_event.is_set():
                now = time.monotonic()

                # Send PING if interval elapsed
                if now - last_ping >= KEEPALIVE_INTERVAL:
                    ping = json.dumps({'type': 'PING'}) + '\n'
                    sock.sendall(ping.encode('utf-8'))
                    last_ping = now

                # Try to read messages (non-blocking-ish with 1s timeout)
                try:
                    buf = self._read_message(sock, buf)
                    if buf is None:
                        # Connection closed
                        return
                    while '\n' in buf:
                        msg, buf = self._parse_next_message(buf)
                        if msg is None:
                            continue
                        self._handle_robot_message(msg, robot_addr)
                except socket.timeout:
                    # No data available, check if we've exceeded keepalive timeout
                    continue

        except (ConnectionResetError, BrokenPipeError, OSError):
            logger.info(f"Connection to {robot_addr} lost")
        except Exception:
            logger.exception(f"Error in connection to {robot_addr}")
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _handle_robot_message(self, msg: dict, robot_addr: str) -> None:
        """Process a message received from the robot."""
        msg_type = msg.get('type', '')

        if msg_type == 'PONG':
            pass  # keepalive response, all good

        elif msg_type == 'UPLOAD_STARTING':
            event = msg.get('event_name', '')
            mtype = msg.get('match_type', '')
            mnum = msg.get('match_number', '')
            logger.info(f"Robot starting upload: {event} {mtype}_{mnum}")

        elif msg_type == 'UPLOAD_COMPLETE':
            event = msg.get('event_name', '')
            mtype = msg.get('match_type', '')
            mnum = msg.get('match_number', '')
            logger.info(f"Robot upload complete: {event} {mtype}_{mnum}")

            if self._on_upload_complete:
                metadata = {
                    'event_name': event,
                    'match_type': mtype,
                    'match_number': mnum,
                }
                try:
                    self._on_upload_complete(metadata)
                except Exception:
                    logger.exception("on_upload_complete callback failed")

        else:
            logger.debug(f"Unknown message from robot: {msg}")

    @staticmethod
    def _read_message(sock: socket.socket, buf: str) -> Optional[str]:
        """Read data until we have at least one newline. Returns None on disconnect."""
        while '\n' not in buf:
            data = sock.recv(4096)
            if not data:
                return None
            buf += data.decode('utf-8')
        return buf

    @staticmethod
    def _parse_next_message(buf: str) -> tuple:
        """Extract the next JSON message from the buffer."""
        idx = buf.index('\n')
        line = buf[:idx].strip()
        remaining = buf[idx + 1:]
        if not line:
            return None, remaining
        try:
            return json.loads(line), remaining
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from robot: {line!r}")
            return None, remaining
