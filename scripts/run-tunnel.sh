#!/bin/bash
set -euo pipefail

LOG_DIR="/home/newjoinee/Mayur/AI-Voice-Agent-Call-Center-Bot/logs"
mkdir -p "$LOG_DIR"

exec /home/newjoinee/bin/cloudflared tunnel --url http://127.0.0.1:8001 --no-autoupdate >> "$LOG_DIR/tunnel.log" 2>&1
