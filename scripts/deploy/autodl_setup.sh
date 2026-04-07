#!/usr/bin/env bash
# =============================================================================
# FaultAtlas — AutoDL Quick Setup
# Target: AutoDL Ubuntu 22.04 + RTX 4090 + CUDA 12.x
#
# Usage:
#   chmod +x scripts/deploy/autodl_setup.sh
#   ./scripts/deploy/autodl_setup.sh
#
# What this does:
#   1. Verify GPU / CUDA environment
#   2. Install uv + Docker (if missing)
#   3. Copy .env.autodl → .env (prompts for OPENAI_API_KEY)
#   4. Create Kafka topics
#   5. Download Qwen model weights via snapshot_download
#   6. Start SGLang server
#   7. Start FaultAtlas services
#   8. Run smoke test
# =============================================================================
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
section() { echo -e "\n${BOLD}══ $* ══${NC}"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# ── Config (override via env) ─────────────────────────────────────────────────
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-7B-Instruct}"
# Default to autodl-tmp (large data disk on AutoDL) to avoid filling root overlay
MODEL_DIR="${MODEL_DIR:-/root/autodl-tmp/models}"
SGLANG_PORT="${SGLANG_PORT:-8100}"
SGLANG_MEM_FRACTION="${SGLANG_MEM_FRACTION:-0.88}"
COMPOSE_FILE="infra/compose/docker-compose.yml"

# Redirect uv download cache to large disk — CUDA wheels are several GB
export UV_CACHE_DIR="${UV_CACHE_DIR:-/root/autodl-tmp/.uv-cache}"

# Detect whether Docker daemon is reachable (not available in AutoDL containers)
docker_available() { docker info &>/dev/null; }

# =============================================================================
section "Step 1 — Environment check"
# =============================================================================

# OS check
if [[ "$(uname -s)" != "Linux" ]]; then
  error "This script is for AutoDL Ubuntu. For Windows local dev, use scripts/deploy/wsl2_setup.sh"
fi
info "OS: $(lsb_release -ds 2>/dev/null || uname -sr)"

# GPU check
if ! command -v nvidia-smi &>/dev/null; then
  error "nvidia-smi not found. Is the NVIDIA driver installed?"
fi
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)
info "GPU: ${GPU_NAME} (${GPU_VRAM})"
nvidia-smi --query-gpu=name,memory.total,driver_version \
  --format=csv,noheader | while IFS=, read -r name mem drv; do
  info "  Driver: $drv"
done

# Check VRAM is at least 20GB (Qwen2.5-7B needs ~16GB bf16 + KV cache headroom)
VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1 | tr -d ' MiB')
if [[ "$VRAM_MB" -lt 20000 ]]; then
  warn "Less than 20GB VRAM detected. Consider using Qwen2.5-3B or enabling quantization."
  warn "To use 4-bit quantization: set SGLANG_EXTRA_ARGS='--quantization awq'"
fi

# =============================================================================
section "Step 2 — Install dependencies"
# =============================================================================

# uv — add to PATH first so repeated runs find the existing binary
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv &>/dev/null; then
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  info "uv installed: $(uv --version)"
else
  info "uv: $(uv --version)"
fi

# Docker
if ! command -v docker &>/dev/null; then
  info "Installing Docker via apt (get.docker.com may be inaccessible)..."
  apt-get update -q && apt-get install -y docker.io
  systemctl start docker 2>/dev/null || true
  systemctl enable docker 2>/dev/null || true
  info "Docker installed: $(docker --version)"
else
  info "Docker: $(docker --version)"
fi

# Docker Compose plugin
if ! docker compose version &>/dev/null; then
  info "Installing Docker Compose v2 plugin..."
  COMPOSE_DIR=/usr/lib/docker/cli-plugins
  mkdir -p "$COMPOSE_DIR"
  curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
    -o "$COMPOSE_DIR/docker-compose"
  chmod +x "$COMPOSE_DIR/docker-compose"
fi
docker compose version &>/dev/null || error "Docker Compose not available. Check network/proxy settings."
info "Docker Compose: $(docker compose version --short)"

# NVIDIA Container Toolkit (for GPU in Docker)
# Skip if running inside a container — GPU passthrough is handled by the host (e.g. AutoDL)
if [ -f /.dockerenv ] || grep -q 'docker\|lxc' /proc/1/cgroup 2>/dev/null; then
  info "Running inside a container — skipping NVIDIA Container Toolkit install (GPU passthrough handled by host)"
elif ! dpkg -l | grep -q nvidia-container-toolkit 2>/dev/null; then
  info "Installing NVIDIA Container Toolkit..."
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update -q
  apt-get install -y nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  service docker restart 2>/dev/null || true
  info "NVIDIA Container Toolkit installed"
else
  info "NVIDIA Container Toolkit: already installed"
fi

# Python deps for model download + SGLang
# Use lockfile hash to detect whether sync is needed, avoiding re-sync on reruns
# while still catching partial/interrupted syncs correctly.
LOCK_HASH_FILE="${REPO_ROOT}/.venv/.uv_lock_hash"
CURRENT_LOCK_HASH=$(sha256sum "${REPO_ROOT}/uv.lock" | awk '{print $1}')
if [[ -d "${REPO_ROOT}/.venv" ]] && \
   [[ -f "$LOCK_HASH_FILE" ]] && \
   [[ "$(cat "$LOCK_HASH_FILE")" == "$CURRENT_LOCK_HASH" ]]; then
  info "Python dependencies up to date — skipping uv sync"
else
  info "Installing Python workspace dependencies..."
  uv sync --all-packages
  echo "$CURRENT_LOCK_HASH" > "$LOCK_HASH_FILE"
fi

# SGLang — isolated venv to avoid huggingface-hub version conflict with workspace deps
# (sglang requires huggingface-hub<1.0; workspace uses huggingface-hub>=1.0)
SGLANG_VENV="${MODEL_DIR}/../.sglang-venv"
SGLANG_PYTHON="${SGLANG_VENV}/bin/python"

if [[ -f "${SGLANG_VENV}/bin/python" ]] && \
   "${SGLANG_PYTHON}" -c "import sglang" &>/dev/null; then
  info "SGLang: already installed in ${SGLANG_VENV}"
else
  info "Installing SGLang in isolated venv: ${SGLANG_VENV}"
  uv venv "${SGLANG_VENV}" --python 3.12
  for attempt in 1 2 3; do
    info "  Install attempt ${attempt}/3..."
    uv pip install "sglang[all]" \
      --python "${SGLANG_PYTHON}" \
      --index-url "https://pypi.tuna.tsinghua.edu.cn/simple" && break
    [[ $attempt -eq 3 ]] && error "SGLang install failed after 3 attempts. Check network/proxy."
    warn "  Attempt ${attempt} failed, retrying in 5s..."
    sleep 5
  done
  info "SGLang installed in isolated venv"
fi

# =============================================================================
section "Step 3 — Configure environment"
# =============================================================================

if [[ ! -f ".env" ]]; then
  if [[ -f "infra/env/.env.autodl" ]]; then
    cp infra/env/.env.autodl .env
    info "Copied infra/env/.env.autodl → .env"
  else
    cp .env.example .env
    info "Copied .env.example → .env"
  fi
fi

# Prompt for required secrets if not set
if ! grep -qE "^OPENAI_API_KEY=sk-" .env 2>/dev/null; then
  echo -n "Enter your OpenAI API key (for embeddings, or press Enter to skip for local embedding): "
  read -r OPENAI_KEY
  if [[ -n "$OPENAI_KEY" ]]; then
    sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${OPENAI_KEY}|" .env
    info "OPENAI_API_KEY set in .env"
  else
    warn "No OpenAI key set. Make sure OPENAI_API_KEY is configured in .env before starting."
  fi
fi

# Inject SGLang URL into .env
sed -i "s|^SGLANG_BASE_URL=.*|SGLANG_BASE_URL=http://localhost:${SGLANG_PORT}/v1|" .env
sed -i "s|^LLM_BACKEND=.*|LLM_BACKEND=sglang|" .env
sed -i "s|^MODEL_NAME=.*|MODEL_NAME=${MODEL_NAME}|" .env
# When running natively (no Docker), service names like 'retriever' won't resolve
sed -i "s|^RETRIEVER_URL=.*|RETRIEVER_URL=http://localhost:8001|" .env

# =============================================================================
section "Step 4 — Download model weights"
# =============================================================================

mkdir -p "$MODEL_DIR"

MODEL_LOCAL_PATH="${MODEL_DIR}/$(echo "$MODEL_NAME" | tr '/' '__')"

# Verify model integrity: config.json must exist and at least one safetensors shard
# must be present and non-empty. snapshot_download is resumable so re-running is safe.
model_complete() {
  local path="$1"
  [[ -f "${path}/config.json" ]] && \
  [[ -s "${path}/config.json" ]] && \
  ls "${path}"/*.safetensors &>/dev/null 2>&1 && \
  [[ $(find "${path}" -name "*.safetensors" -size +100M | wc -l) -gt 0 ]]
}

if model_complete "$MODEL_LOCAL_PATH"; then
  info "Model already complete at ${MODEL_LOCAL_PATH}"
else
  [[ -d "$MODEL_LOCAL_PATH" ]] && warn "Incomplete model found — resuming download..."
  info "Downloading ${MODEL_NAME} to ${MODEL_LOCAL_PATH}..."
  info "This may take 10–20 minutes on AutoDL (model is ~15 GB)."

  uv run python - <<PYEOF
from huggingface_hub import snapshot_download
import os

model_name = os.environ.get("MODEL_NAME", "${MODEL_NAME}")
local_path = "${MODEL_LOCAL_PATH}"

print(f"Downloading {model_name} → {local_path}")
snapshot_download(
    repo_id=model_name,
    local_dir=local_path,
    ignore_patterns=["*.msgpack", "*.h5", "flax_model*"],
)
print(f"Download complete: {local_path}")
PYEOF

  model_complete "$MODEL_LOCAL_PATH" || error "Model download appears incomplete. Check disk space and retry."
  info "Model downloaded: ${MODEL_LOCAL_PATH}"
fi

# Update MODEL_PATH in .env for SGLang server
grep -q "^MODEL_PATH=" .env && \
  sed -i "s|^MODEL_PATH=.*|MODEL_PATH=${MODEL_LOCAL_PATH}|" .env || \
  echo "MODEL_PATH=${MODEL_LOCAL_PATH}" >> .env

# =============================================================================
section "Step 5 — Start infrastructure (MongoDB + Redis)"
# =============================================================================

if docker_available; then
  info "Starting MongoDB and Redis via Docker Compose..."
  docker compose -f "$COMPOSE_FILE" up mongo redis -d

  info "Waiting for MongoDB to be healthy..."
  for i in {1..30}; do
    if docker compose -f "$COMPOSE_FILE" exec -T mongo \
      mongosh --eval "db.adminCommand('ping')" &>/dev/null; then
      info "MongoDB ready"
      break
    fi
    [[ $i -eq 30 ]] && error "MongoDB failed to start after 30 seconds"
    sleep 1
  done

  info "Waiting for Redis to be healthy..."
  for i in {1..20}; do
    if docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping &>/dev/null; then
      info "Redis ready"
      break
    fi
    [[ $i -eq 20 ]] && error "Redis failed to start after 20 seconds"
    sleep 1
  done
else
  warn "Docker daemon not available — starting MongoDB and Redis natively"

  # MongoDB
  if ! command -v mongod &>/dev/null; then
    info "Installing MongoDB 7..."
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
      gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg
    echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
      https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
      > /etc/apt/sources.list.d/mongodb-org-7.0.list
    apt-get update -q && apt-get install -y mongodb-org
  fi
  mkdir -p /var/lib/mongodb /var/log/mongodb
  if ! mongosh --eval "db.adminCommand('ping')" &>/dev/null; then
    mongod --fork --logpath /var/log/mongodb/mongod.log --dbpath /var/lib/mongodb
    for i in {1..20}; do
      mongosh --eval "db.adminCommand('ping')" &>/dev/null && break
      [[ $i -eq 20 ]] && error "MongoDB failed to start"
      sleep 1
    done
  fi
  info "MongoDB ready"

  # Redis
  if ! command -v redis-server &>/dev/null; then
    info "Installing Redis..."
    apt-get install -y redis-server
  fi
  if ! redis-cli ping &>/dev/null; then
    redis-server --daemonize yes --logfile /var/log/redis.log
    for i in {1..10}; do
      redis-cli ping &>/dev/null && break
      [[ $i -eq 10 ]] && error "Redis failed to start"
      sleep 1
    done
  fi
  info "Redis ready"

  # Update .env to use localhost instead of Docker service names
  sed -i "s|^MONGO_URI=.*|MONGO_URI=mongodb://localhost:27017|" .env
  sed -i "s|^REDIS_URL=.*|REDIS_URL=redis://localhost:6379/0|" .env
  info "Updated .env: MONGO_URI and REDIS_URL → localhost"
fi

# ninja — required by flashinfer JIT kernel compilation at SGLang startup
if ! command -v ninja &>/dev/null; then
  info "Installing ninja (required by flashinfer)..."
  apt-get install -y ninja-build
  # Ubuntu installs as 'ninja-build'; flashinfer subprocess calls 'ninja'
  ln -sf /usr/bin/ninja-build /usr/local/bin/ninja
  info "ninja installed: $(ninja --version)"
else
  info "ninja: $(ninja --version)"
fi

# =============================================================================
section "Step 6 — Start SGLang model server"
# =============================================================================

# Check if SGLang is already running
if curl -sf "http://localhost:${SGLANG_PORT}/health" &>/dev/null; then
  info "SGLang server already running at port ${SGLANG_PORT}"
else
  info "Starting SGLang server (${MODEL_NAME})..."
  info "Port: ${SGLANG_PORT} | Mem fraction: ${SGLANG_MEM_FRACTION}"

  # Start in background, write logs to file
  SGLANG_LOG="${REPO_ROOT}/logs/sglang.log"
  mkdir -p "${REPO_ROOT}/logs"

  nohup "${SGLANG_PYTHON}" -m sglang.launch_server \
    --model-path "${MODEL_LOCAL_PATH}" \
    --host 0.0.0.0 \
    --port "${SGLANG_PORT}" \
    --mem-fraction-static "${SGLANG_MEM_FRACTION}" \
    --enable-torch-compile \
    ${SGLANG_EXTRA_ARGS:-} \
    > "${SGLANG_LOG}" 2>&1 &

  SGLANG_PID=$!
  echo $SGLANG_PID > "${REPO_ROOT}/logs/sglang.pid"
  info "SGLang PID: ${SGLANG_PID} — logs at ${SGLANG_LOG}"

  info "Waiting for SGLang to be ready (first run with --enable-torch-compile takes 5–10 min for kernel autotuning)..."
  for i in {1..600}; do
    if curl -sf "http://localhost:${SGLANG_PORT}/health" &>/dev/null; then
      info "SGLang server ready"
      break
    fi
    # Check if the process died
    if ! kill -0 "$SGLANG_PID" 2>/dev/null; then
      error "SGLang server process died. Check ${SGLANG_LOG} for details."
    fi
    [[ $i -eq 600 ]] && error "SGLang failed to start after 600s. Check ${SGLANG_LOG}"
    [[ $((i % 10)) -eq 0 ]] && info "  Still loading... (${i}s)"
    sleep 1
  done
fi

# =============================================================================
section "Step 7 — Start FaultAtlas services"
# =============================================================================

LOG_DIR="${REPO_ROOT}/logs"
mkdir -p "$LOG_DIR"

if docker_available; then
  info "Starting API, Retriever, and Ingestion via Docker Compose..."
  docker compose -f "$COMPOSE_FILE" up api retriever ingestion -d --build

  info "Waiting for API to be ready..."
  for i in {1..30}; do
    if curl -sf "http://localhost:8000/health" &>/dev/null; then
      info "API ready at http://localhost:8000"
      break
    fi
    [[ $i -eq 30 ]] && error "API failed to start. Check: docker compose -f ${COMPOSE_FILE} logs api"
    sleep 2
  done
else
  info "Starting API, Retriever, and Ingestion natively via uv..."

  nohup uv run --package faultatlas-api uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/api.log" 2>&1 &
  echo $! > "$LOG_DIR/api.pid"

  nohup uv run --package faultatlas-retriever uvicorn app.main:app \
    --host 0.0.0.0 --port 8001 \
    > "$LOG_DIR/retriever.log" 2>&1 &
  echo $! > "$LOG_DIR/retriever.pid"

  nohup uv run --package faultatlas-ingestion uvicorn app.main:app \
    --host 0.0.0.0 --port 8002 \
    > "$LOG_DIR/ingestion.log" 2>&1 &
  echo $! > "$LOG_DIR/ingestion.pid"

  info "Waiting for API to be ready..."
  for i in {1..30}; do
    if curl -sf "http://localhost:8000/health" &>/dev/null; then
      info "API ready at http://localhost:8000"
      break
    fi
    [[ $i -eq 30 ]] && error "API failed to start. Check: $LOG_DIR/api.log"
    sleep 2
  done
  info "Logs: $LOG_DIR/{api,retriever,ingestion}.log"
fi

# =============================================================================
section "Step 8 — Seed knowledge base"
# =============================================================================

read -rp "Seed sample data into knowledge base? [Y/n]: " SEED_CONFIRM
SEED_CONFIRM="${SEED_CONFIRM:-Y}"
if [[ "${SEED_CONFIRM^^}" == "Y" ]]; then
  uv run python scripts/seed_data.py
  info "Seed complete"
else
  info "Skipping seed. Run manually: uv run python scripts/seed_data.py"
fi

# =============================================================================
section "Step 9 — Smoke test"
# =============================================================================

read -rp "Run smoke test? [Y/n]: " SMOKE_CONFIRM
SMOKE_CONFIRM="${SMOKE_CONFIRM:-Y}"
if [[ "${SMOKE_CONFIRM^^}" == "Y" ]]; then
  ./scripts/smoke_test.sh
fi

# =============================================================================
section "Setup complete"
# =============================================================================

echo ""
echo -e "${GREEN}FaultAtlas is running on AutoDL.${NC}"
echo ""
echo "  API docs:       http://localhost:8000/docs"
echo "  SGLang server:  http://localhost:${SGLANG_PORT}/v1"
echo "  SGLang logs:    tail -f ${REPO_ROOT}/logs/sglang.log"
echo ""
echo "  Run benchmark:  curl -X POST http://localhost:8000/benchmark/run -H 'X-API-Key: changeme-local-dev'"
echo "  Stop all:       ./scripts/deploy/stop.sh"
echo "  View logs:      docker compose -f ${COMPOSE_FILE} logs -f"
echo ""
