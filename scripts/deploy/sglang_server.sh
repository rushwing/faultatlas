#!/usr/bin/env bash
# =============================================================================
# FaultAtlas — SGLang Server Management
# Isolated from main setup so it can be called independently.
#
# Usage:
#   ./scripts/deploy/sglang_server.sh start   [model_path]
#   ./scripts/deploy/sglang_server.sh stop
#   ./scripts/deploy/sglang_server.sh status
#   ./scripts/deploy/sglang_server.sh logs
#   ./scripts/deploy/sglang_server.sh restart [model_path]
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs"
PID_FILE="${LOG_DIR}/sglang.pid"
LOG_FILE="${LOG_DIR}/sglang.log"
mkdir -p "$LOG_DIR"

# Load .env if present
[[ -f "${REPO_ROOT}/.env" ]] && set -a && source "${REPO_ROOT}/.env" && set +a

SGLANG_PORT="${SGLANG_PORT:-8100}"
MODEL_PATH="${MODEL_PATH:-${MODEL_DIR:-/root/models}/Qwen__Qwen2.5-7B-Instruct}"
SGLANG_MEM_FRACTION="${SGLANG_MEM_FRACTION:-0.88}"
SGLANG_EXTRA_ARGS="${SGLANG_EXTRA_ARGS:-}"

CMD="${1:-status}"
MODEL_OVERRIDE="${2:-}"
[[ -n "$MODEL_OVERRIDE" ]] && MODEL_PATH="$MODEL_OVERRIDE"

_is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

_health_check() {
  curl -sf "http://localhost:${SGLANG_PORT}/health" &>/dev/null
}

case "$CMD" in
  start)
    if _is_running && _health_check; then
      echo "SGLang server already running (PID $(cat "$PID_FILE"))"
      exit 0
    fi

    if [[ ! -d "$MODEL_PATH" ]]; then
      echo "ERROR: Model path not found: ${MODEL_PATH}"
      echo "Run autodl_setup.sh first, or set MODEL_PATH in .env"
      exit 1
    fi

    echo "Starting SGLang server..."
    echo "  Model:       ${MODEL_PATH}"
    echo "  Port:        ${SGLANG_PORT}"
    echo "  Mem frac:    ${SGLANG_MEM_FRACTION}"
    echo "  Extra args:  ${SGLANG_EXTRA_ARGS:-none}"
    echo "  Log:         ${LOG_FILE}"

    # Install SGLang if not present
    if ! uv run --package faultatlas-api python -c "import sglang" 2>/dev/null; then
      echo "Installing sglang..."
      uv pip install "sglang[all]>=0.3"
    fi

    nohup uv run python -m sglang.launch_server \
      --model-path "${MODEL_PATH}" \
      --host 0.0.0.0 \
      --port "${SGLANG_PORT}" \
      --mem-fraction-static "${SGLANG_MEM_FRACTION}" \
      --enable-torch-compile \
      ${SGLANG_EXTRA_ARGS} \
      >> "${LOG_FILE}" 2>&1 &

    echo $! > "$PID_FILE"
    echo "SGLang PID: $(cat "$PID_FILE")"

    echo -n "Waiting for server to be ready"
    for i in {1..120}; do
      if _health_check; then
        echo " ready (${i}s)"
        break
      fi
      if ! _is_running; then
        echo ""
        echo "ERROR: Server process died. Last 20 lines of log:"
        tail -20 "$LOG_FILE"
        exit 1
      fi
      [[ $i -eq 120 ]] && echo "" && echo "ERROR: Timeout waiting for SGLang" && exit 1
      echo -n "."
      sleep 1
    done

    echo "SGLang server running at http://localhost:${SGLANG_PORT}/v1"
    ;;

  stop)
    if _is_running; then
      PID=$(cat "$PID_FILE")
      echo "Stopping SGLang (PID $PID)..."
      kill "$PID"
      rm -f "$PID_FILE"
      echo "Stopped"
    else
      echo "SGLang not running"
      rm -f "$PID_FILE"
    fi
    ;;

  restart)
    "$0" stop
    sleep 2
    "$0" start "${MODEL_OVERRIDE:-}"
    ;;

  status)
    if _is_running && _health_check; then
      PID=$(cat "$PID_FILE")
      echo "SGLang server: RUNNING (PID $PID, port ${SGLANG_PORT})"
      # Show GPU memory usage
      nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null | \
        awk '{printf "  GPU memory: %s / %s\n", $1, $2}' || true
    elif _is_running; then
      echo "SGLang server: PROCESS RUNNING but health check failed (port ${SGLANG_PORT})"
    else
      echo "SGLang server: STOPPED"
    fi
    ;;

  logs)
    if [[ -f "$LOG_FILE" ]]; then
      tail -f "$LOG_FILE"
    else
      echo "No log file found at ${LOG_FILE}"
    fi
    ;;

  *)
    echo "Usage: $0 {start|stop|restart|status|logs} [model_path]"
    exit 1
    ;;
esac
