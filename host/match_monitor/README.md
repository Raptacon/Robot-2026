# match_monitor

Receives robot log files over HTTP and analyzes them after each match.

The host laptop polls for the roboRIO via a TCP control channel (port 5805).
Once connected, the robot discovers the host IP from the socket and uploads
log files via HTTP. When uploads finish, the robot sends `UPLOAD_COMPLETE`
over TCP and the server runs .wpilog analysis automatically.

## Setup

```
pip install -r host/match_monitor/requirements.txt
```

## Running

```
python -m host.match_monitor
```

Options:
- `--port` — HTTP port to listen on (default: 5800)
- `--bind` — address to bind to (default: 0.0.0.0)
- `--output-dir` — where to save logs (default: `~/Documents/robotlogs`)

## Windows Firewall (first-time setup)

Ports 5800 (HTTP log receiver) and 5805 (TCP control channel) require
firewall rules. Run once in an **elevated PowerShell** (Run as Administrator):

```powershell
New-NetFirewallRule -DisplayName "FRC Match Monitor HTTP"    -Direction Inbound  -Protocol TCP -LocalPort 5800 -Action Allow
New-NetFirewallRule -DisplayName "FRC Match Monitor Control" -Direction Outbound -Protocol TCP -RemotePort 5805 -Action Allow
```

## Output

Files are saved under `<output-dir>/<event>/<match_type>_<match_number>/`.

After all uploads complete, the server writes `match_summary.json` to the
match directory containing:
- Brownout count and timestamps
- Disconnect count and timestamps
- Voltage stats (start, end, avg, min, max)
- Match duration
- Mode transitions (disabled → auto → teleop → disabled)

## HTTP Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | Server health check |
| POST | `/upload` | Receive a log file (headers: `X-Filename`, `X-Event-Name`, `X-Match-Type`, `X-Match-Number`; supports `Content-Encoding: deflate`) |
| GET | `/check` | SHA-256 of a stored file (header: `X-Filename`) |

## TCP Control Protocol (port 5805)

| Message | Direction | Payload |
|---------|-----------|---------|
| `HELLO` | Host → Robot | `{"type":"HELLO","http_port":5800}` |
| `HELLO_ACK` | Robot → Host | `{"type":"HELLO_ACK"}` |
| `PING` / `PONG` | Host ↔ Robot | Keepalive every 10s |
| `UPLOAD_STARTING` | Robot → Host | Match metadata |
| `UPLOAD_COMPLETE` | Robot → Host | Match metadata — triggers analysis |
