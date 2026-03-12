# match_monitor

Post-match analysis server for FRC Team 3200. Receives robot log files over HTTP,
analyzes them after each match, correlates Driver Station logs, fetches official
match results from The Blue Alliance, and posts a summary to Discord.

## How It Works

1. Host laptop starts `match_monitor` and polls for the roboRIO via TCP (port 5805)
2. Robot connects, discovers the host IP from the socket, and uploads `.wpilog` files over HTTP
3. Robot sends `UPLOAD_COMPLETE` over TCP when done
4. Server analyzes `.wpilog` files, collects DS logs, fetches TBA data, posts to Discord, and writes `match_summary.json`

## Setup

```bash
pip install -r host/requirements.txt
```

### Windows Firewall (first-time, run once as Administrator)

```powershell
New-NetFirewallRule -DisplayName "FRC Match Monitor HTTP"    -Direction Inbound  -Protocol TCP -LocalPort 5800 -Action Allow
New-NetFirewallRule -DisplayName "FRC Match Monitor Control" -Direction Outbound -Protocol TCP -RemotePort 5805 -Action Allow
```

## Running

```bash
python -m host.match_monitor
python -m host.match_monitor --port 5800 --output-dir "D:\FRC\Logs"
```

Options:
| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `5800` | HTTP port |
| `--bind` | `0.0.0.0` | Bind address |
| `--output-dir` | `C:\Users\Public\Documents\FRC\Log Files\WPILogs` | Log output root |
| `--debug` | off | Enable DEBUG log level |

## Configuration

Create `match_monitor_config.json` in the output directory (copy from
`host/match_monitor/match_monitor_config.example.json`).  The file is
excluded from git — it contains API keys.

```json
{
    "team_number": 3200,
    "tba_api_key": "YOUR_TBA_KEY",
    "frc_events_username": "YOUR_USERNAME",
    "frc_events_auth_key": "YOUR_AUTH_KEY",
    "discord_webhook_url": "https://discord.com/api/webhooks/..."
}
```

All fields are optional — the server runs without any of them, but with
reduced functionality (no official match data, no Discord posts).

| Field | Where to get it |
|-------|----------------|
| `tba_api_key` | https://www.thebluealliance.com → Account → Read API Keys |
| `frc_events_username` / `frc_events_auth_key` | https://frc-events.firstinspires.org/services/api/register |
| `discord_webhook_url` | Discord server → Server Settings → Integrations → Webhooks → New Webhook → Copy URL |

The webhook URL can also be set at runtime from the console prompt (see below).

## Interactive Console

The server runs an interactive `monitor>` prompt alongside log output.

### Robot commands (require TCP connection)
| Command | Action |
|---------|--------|
| `list` | List log files on robot with sizes and upload status |
| `upload` | Force robot to start uploading immediately |
| `stop` | Stop an in-progress upload |
| `clear-manifest` | Delete upload manifests so all logs re-upload |

### Connection
| Command | Action |
|---------|--------|
| `status` | Show connection state, uptime, polling addresses |
| `connect` | Resume polling / reconnect |
| `disconnect` | Close connection and stop polling |

### Discord
| Command | Action |
|---------|--------|
| `discord` | Show current webhook URL (masked) |
| `discord <url>` | Set/update webhook URL — takes effect immediately and saves to config |
| `discord off` | Disable Discord notifications |
| `discord test` | Send a test message to verify the webhook |

### Logging
| Command | Action |
|---------|--------|
| `log` | Show current console and file log levels |
| `log <level>` | Set console log level (`debug` / `info` / `warning` / `error`) |
| `log off` / `log on` | Disable/re-enable console logging (file log unaffected) |
| `log file <level>` | Set file log level |
| `log file off` / `on` | Disable/re-enable file logging |
| `log rotate` | Close current log file and open a new timestamped one |

## Output

Files are saved under `<output-dir>/<event>/<match_type>_<match_number>/`.

After analysis completes, `match_summary.json` is written to the match directory:

```json
{
  "event_name": "2026calas",
  "match_type": "Qualification",
  "match_number": "12",
  "analyzed_at": "...",
  "brownout_count": 0,
  "disconnect_count": 1,
  "disconnect_timestamps_sec": [47.3],
  "match_duration_seconds": 152.4,
  "voltage": {
    "start": 12.847, "end": 11.923, "average": 12.301,
    "min": 11.684, "max": 12.901, "samples": 7620
  },
  "mode_transitions": [...],
  "ds_log": {
    "summary": {
      "avg_packet_loss_pct": 0.2, "avg_trip_time_ms": 3.1,
      "max_trip_time_ms": 18, "min_battery_v": 11.684
    },
    "events": [...]
  },
  "official_match": {
    "result": "win", "our_score": 45, "opponent_score": 38,
    "our_alliance": "red", "video_url": "https://youtube.com/..."
  },
  "event_stats": {
    "opr": 34.7, "dpr": 12.3, "ccwm": 22.4,
    "rank": 5, "wins": 7, "losses": 2
  }
}
```

### Driver Station log correlation

DS logs (`*.dslog` / `*.dsevents`) are automatically located from
`C:\Users\Public\Documents\FRC\Log Files\` using the wall-clock time
embedded in the `.wpilog` file (`systemTime` entry). Files within a
5-minute window are copied into the match directory and parsed.

### Discord embed

When `discord_webhook_url` is configured, a rich embed is posted after
each match with: result/score, alliance teams, battery voltage, brownouts,
DS packet loss and latency, OPR/rank, robot code git hash, controller
config hash verification, TBA/FRC Events/video links, and a random
sci-fi/fantasy/zombie quote.

## HTTP Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Server health check |
| `POST` | `/upload` | Receive a log file (headers: `X-Filename`, `X-Event-Name`, `X-Match-Type`, `X-Match-Number`; supports `Content-Encoding: deflate`) |
| `GET` | `/check` | SHA-256 of a stored file (header: `X-Filename`) |

## TCP Control Protocol (port 5805)

| Message | Direction | Payload |
|---------|-----------|---------|
| `HELLO` | Host → Robot | `{"type":"HELLO","http_port":5800}` |
| `HELLO_ACK` | Robot → Host | `{"type":"HELLO_ACK"}` |
| `PING` / `PONG` | Host ↔ Robot | Keepalive every 10 s |
| `UPLOAD_STARTING` | Robot → Host | Match metadata |
| `UPLOAD_COMPLETE` | Robot → Host | Match metadata — triggers analysis |
| `LIST_LOGS` | Host → Robot | Request file listing |
| `LIST_LOGS_RESPONSE` | Robot → Host | `{"files":[{"name":...,"size":...,"uploaded":...}]}` |
| `FORCE_UPLOAD` | Host → Robot | Start uploading now |
| `FORCE_UPLOAD_ACK` | Robot → Host | Acknowledged |
| `STOP_UPLOAD` | Host → Robot | Abort in-progress upload |
| `STOP_UPLOAD_ACK` | Robot → Host | Acknowledged |
| `CLEAR_MANIFEST` | Host → Robot | Delete manifest files; robot finishes current file, clears, restarts upload |
| `MANIFEST_CLEARED` | Robot → Host | `{"count": N}` manifests deleted |

## Controller Config Hash Verification

The robot should publish a `controller_config_hash` NT string entry containing
the SHA-256 (first 8 hex chars) of `data/controller.yaml`:

```python
import hashlib
from pathlib import Path

hash_val = hashlib.sha256(Path('data/controller.yaml').read_bytes()).hexdigest()[:8]
# Publish to NT as 'controller_config_hash'
```

The Discord embed will show ✅ if the robot's hash matches the local repo file,
or ⚠ mismatch if they differ.
