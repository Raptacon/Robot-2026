# match_monitor

HTTP server that receives robot log files and analyzes them after each match.

## Setup

```
pip install -r host/match_monitor/requirements.txt
```

## Running

```
python -m host.match_monitor
```

Options:
- `--port` — port to listen on (default: 5800)
- `--bind` — address to bind to (default: 0.0.0.0)
- `--output-dir` — where to save logs (default: `~/Documents/robotlogs`)

## Windows Firewall (first-time setup)

Port 5810 requires a firewall rule. Run once in an **elevated PowerShell** (Run as Administrator):

```powershell
New-NetFirewallRule -DisplayName "FRC Match Monitor In"  -Direction Inbound  -Protocol TCP -LocalPort 5800 -Action Allow
New-NetFirewallRule -DisplayName "FRC Match Monitor Out" -Direction Outbound -Protocol TCP -LocalPort 5800 -Action Allow
```

## Output

Files are saved under `<output-dir>/<event>/<match_type>_<match_number>/`.

After all uploads complete, the robot sends `POST /match-complete` and the server writes `match_summary.json` to the match directory containing:
- Brownout count and timestamps
- Disconnect count and timestamps
- Voltage stats (start, end, avg, min, max)
- Match duration
- Mode transitions (disabled → auto → teleop → disabled)

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | Server health check |
| POST | `/upload` | Receive a log file (headers: `X-Filename`, `X-Event-Name`, `X-Match-Type`, `X-Match-Number`) |
| GET | `/check` | SHA-256 of a stored file (header: `X-Filename`) |
| POST | `/match-complete` | Trigger log analysis (body: `{event_name, match_type, match_number}`) |
