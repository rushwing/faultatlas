#!/usr/bin/env bash
# Stop all FaultAtlas services (Docker containers + SGLang server)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/compose/docker-compose.yml"

echo "Stopping Docker services..."
docker compose -f "$COMPOSE_FILE" down

# Stop SGLang server
PID_FILE="${REPO_ROOT}/logs/sglang.pid"
if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping SGLang server (PID $PID)..."
    kill "$PID"
    rm "$PID_FILE"
    echo "SGLang stopped"
  else
    echo "SGLang PID $PID not running (already stopped)"
    rm -f "$PID_FILE"
  fi
else
  # Try to find by port
  SGLANG_PORT="${SGLANG_PORT:-8100}"
  if command -v fuser &>/dev/null && fuser "${SGLANG_PORT}/tcp" &>/dev/null; then
    fuser -k "${SGLANG_PORT}/tcp"
    echo "Killed process on port ${SGLANG_PORT}"
  fi
fi

echo "All stopped."
