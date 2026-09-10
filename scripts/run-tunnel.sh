#!/bin/bash
# Expose the local backend over HTTPS via a Cloudflare quick tunnel.
#
# Paths are derived from the repo location and the cloudflared binary is looked
# up on PATH; both were previously hardcoded to one developer's home directory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
CLOUDFLARED="${CLOUDFLARED:-$(command -v cloudflared || true)}"

if [ -z "$CLOUDFLARED" ]; then
  echo "cloudflared not found on PATH. Install it or set CLOUDFLARED=/path/to/cloudflared" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
exec "$CLOUDFLARED" tunnel --url "$BACKEND_URL" --no-autoupdate >> "$LOG_DIR/tunnel.log" 2>&1
