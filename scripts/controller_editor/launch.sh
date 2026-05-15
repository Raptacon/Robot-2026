#!/usr/bin/env bash
# One-shot launcher for the controller web editor (macOS / Linux).
#
# What it does, in order:
#   1. Find or create venv/ at the repo root (uses `python3` on PATH).
#   2. Install requirements.txt + host/requirements.txt if anything is missing.
#   3. Ensure Node.js + npm are installed (auto-install via brew on
#      macOS; print apt/dnf instructions on Linux).
#   4. Launch `python -m host.controller_web_editor` -- the server
#      builds the SPA on startup if static/ is missing or stale.
#   5. Open a browser once the server is listening.
#
# Idempotent: re-running just re-launches the server.  Skips pip when
# the install stamp matches.

set -euo pipefail

# Repo root = parent of scripts/controller_editor
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)
cd "$repo_root"

venv="$repo_root/venv"
venv_python="$venv/bin/python3"
stamp="$venv/.controller_editor_install.stamp"

find_system_python() {
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    echo "No Python interpreter found on PATH.  Install Python 3.10+ and retry." >&2
    return 1
}

if [[ ! -x "$venv_python" ]]; then
    echo "Creating venv at $venv ..."
    sys_python=$(find_system_python)
    "$sys_python" -m venv "$venv"
    rm -f "$stamp"
fi

# Hash the requirements files; only install when the contents change.
req_files=(
    "$repo_root/requirements.txt"
    "$repo_root/host/requirements.txt"
)
if command -v sha1sum >/dev/null 2>&1; then
    hasher='sha1sum'
elif command -v shasum >/dev/null 2>&1; then
    hasher='shasum -a 1'
else
    hasher='cat'  # fall back to raw concat -- forces every-run reinstall
fi
req_hash=$($hasher "${req_files[@]}" 2>/dev/null | awk '{print $1}' | tr '\n' ',')

need_install=1
if [[ -f "$stamp" ]] && [[ "$(cat "$stamp")" == "$req_hash" ]]; then
    need_install=0
fi

if [[ "$need_install" -eq 1 ]]; then
    echo "Installing Python deps (this only re-runs when requirements change) ..."
    "$venv_python" -m pip install --upgrade pip --quiet
    for req in "${req_files[@]}"; do
        "$venv_python" -m pip install -r "$req" --quiet
    done
    printf '%s' "$req_hash" > "$stamp"
fi

ensure_node() {
    if command -v npm >/dev/null 2>&1; then return 0; fi

    echo "Node.js / npm not found on PATH."
    case "$(uname -s)" in
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                echo "Installing Node.js via Homebrew (brew install node) ..."
                brew install node
            else
                cat >&2 <<'EOF'
Node.js is required to build the controller editor SPA.  Homebrew
isn't available to auto-install it.  Install Node.js (LTS) manually:
    https://nodejs.org/en/download
Then re-run this launcher.
EOF
                exit 1
            fi
            ;;
        Linux)
            cat >&2 <<'EOF'
Node.js is required to build the controller editor SPA.  Install it
via your distro's package manager (sudo is required):
    Ubuntu/Debian:  sudo apt-get update && sudo apt-get install -y nodejs npm
    Fedora/RHEL:    sudo dnf install -y nodejs npm
    Arch:           sudo pacman -S nodejs npm
Or grab the official binaries from https://nodejs.org/en/download
Then re-run this launcher.
EOF
            exit 1
            ;;
        *)
            echo "Install Node.js LTS from https://nodejs.org/en/download then re-run." >&2
            exit 1
            ;;
    esac

    # Sanity-check after install.
    if ! command -v npm >/dev/null 2>&1; then
        echo "Node install reported success but npm still isn't on PATH.  Open a new terminal and re-run." >&2
        exit 1
    fi
    echo "Node.js installed: $(node --version)"
}

ensure_node

# Open a browser shortly after the server starts listening.
port=8071
(
    for _ in $(seq 1 40); do
        sleep 0.25
        if (echo > "/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
            url="http://127.0.0.1:$port"
            if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url"
            elif command -v open >/dev/null 2>&1; then open "$url"
            fi
            break
        fi
    done
) &

echo "Starting server on http://127.0.0.1:$port (Ctrl+C to stop)"
exec "$venv_python" -m host.controller_web_editor --port "$port"
