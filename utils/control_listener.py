"""TCP control listener for receiving host connections.

The host laptop connects to the robot on port 5805. The robot learns the
host's IP from the accepted socket and uses it for HTTP log uploads.
"""

import json
import logging
import socket
import threading
from typing import Optional

from ntcore.util import ntproperty

logger = logging.getLogger(__name__)

CONTROL_PORT = 5805


class ControlListener:
    """Listens for a host TCP connection and maintains a keepalive channel.

    Protocol (newline-delimited JSON over TCP):
        Host → Robot: HELLO {http_port}
        Robot → Host: HELLO_ACK
        Host → Robot: PING
        Robot → Host: PONG
        Robot → Host: UPLOAD_STARTING / UPLOAD_COMPLETE
    """

    status = ntproperty('/ControlListener/status', 'idle',
                         writeDefault=True, persistent=False)

    def __init__(self) -> None:
        self._host_ip: Optional[str] = None
        self._http_port: Optional[int] = None
        self._conn: Optional[socket.socket] = None
        self._conn_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    @property
    def host_ip(self) -> Optional[str]:
        return self._host_ip

    @property
    def http_port(self) -> Optional[int]:
        return self._http_port

    @property
    def is_connected(self) -> bool:
        return self._host_ip is not None and self._conn is not None

    def start(self) -> None:
        """Start the listener thread. Safe to call multiple times."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def send_message(self, msg: dict) -> bool:
        """Send a JSON message to the connected host. Returns False if not connected."""
        with self._conn_lock:
            if self._conn is None:
                return False
            try:
                data = json.dumps(msg) + '\n'
                self._conn.sendall(data.encode('utf-8'))
                return True
            except Exception:
                logger.exception("Failed to send message to host")
                return False

    def send_upload_starting(self, event_name: str, match_type: str,
                             match_number: str) -> bool:
        return self.send_message({
            'type': 'UPLOAD_STARTING',
            'event_name': event_name,
            'match_type': match_type,
            'match_number': match_number,
        })

    def send_upload_complete(self, event_name: str, match_type: str,
                             match_number: str) -> bool:
        return self.send_message({
            'type': 'UPLOAD_COMPLETE',
            'event_name': event_name,
            'match_type': match_type,
            'match_number': match_number,
        })

    def _listen_loop(self) -> None:
        """Main listener loop — binds, accepts, handles one connection at a time."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('0.0.0.0', CONTROL_PORT))
        server_sock.listen(1)
        logger.info(f"ControlListener listening on port {CONTROL_PORT}")
        self.status = 'listening'
        print(f"[ControlListener] Listening on port {CONTROL_PORT}")

        while True:
            try:
                conn, addr = server_sock.accept()
                print(f"[ControlListener] Connection from {addr[0]}:{addr[1]}")
                self._handle_connection(conn, addr)
            except Exception:
                logger.exception("Error accepting connection")

    def _handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """Handle a single host connection: handshake, then keepalive loop."""
        # Close any existing connection
        with self._conn_lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._conn = conn

        conn.settimeout(35)  # slightly more than keepalive interval + timeout

        try:
            buf = ''
            # Read HELLO message
            buf = self._read_message(conn, buf)
            if buf is None:
                return

            msg, buf = self._parse_next_message(buf)
            if msg is None or msg.get('type') != 'HELLO':
                logger.warning(f"Expected HELLO, got: {msg}")
                return

            host_ip = addr[0]
            http_port = msg.get('http_port', 5800)
            self._host_ip = host_ip
            self._http_port = int(http_port)

            # Send HELLO_ACK
            ack = json.dumps({'type': 'HELLO_ACK'}) + '\n'
            conn.sendall(ack.encode('utf-8'))

            self.status = f'connected ({host_ip})'
            logger.info(f"Host connected: {host_ip}, HTTP port {http_port}")
            print(f"[ControlListener] Host connected: {host_ip}:{http_port}")

            # Keepalive loop — respond to PINGs
            while True:
                buf = self._read_message(conn, buf)
                if buf is None:
                    break
                msg, buf = self._parse_next_message(buf)
                if msg is None:
                    continue
                if msg.get('type') == 'PING':
                    pong = json.dumps({'type': 'PONG'}) + '\n'
                    conn.sendall(pong.encode('utf-8'))
                else:
                    logger.debug(f"Unexpected message from host: {msg}")

        except socket.timeout:
            logger.warning("Host connection timed out (no keepalive)")
            print("[ControlListener] Host connection timed out")
        except (ConnectionResetError, BrokenPipeError, OSError):
            logger.info("Host disconnected")
            print("[ControlListener] Host disconnected")
        except Exception:
            logger.exception("Error in host connection handler")
        finally:
            self._host_ip = None
            self._http_port = None
            with self._conn_lock:
                self._conn = None
            try:
                conn.close()
            except Exception:
                pass
            self.status = 'listening'
            print("[ControlListener] Back to listening")

    @staticmethod
    def _read_message(conn: socket.socket, buf: str) -> Optional[str]:
        """Read data from socket until we have at least one newline. Returns updated buf or None on disconnect."""
        while '\n' not in buf:
            data = conn.recv(4096)
            if not data:
                return None
            buf += data.decode('utf-8')
        return buf

    @staticmethod
    def _parse_next_message(buf: str) -> tuple:
        """Extract the next JSON message from the buffer. Returns (msg_dict, remaining_buf)."""
        idx = buf.index('\n')
        line = buf[:idx].strip()
        remaining = buf[idx + 1:]
        if not line:
            return None, remaining
        try:
            return json.loads(line), remaining
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from host: {line!r}")
            return None, remaining
