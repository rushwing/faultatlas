#!/usr/bin/env bash
# =============================================================================
# FaultAtlas — Local Windows Development Setup (inside WSL2 Ubuntu)
#
# Prerequisites (run these in Windows first):
#   1. Enable WSL2:          wsl --install
#   2. Install Ubuntu 22.04: wsl --install -d Ubuntu-22.04
#   3. Install Docker Desktop with WSL2 backend enabled
#   4. (Optional, for local GPU) Windows 11 + NVIDIA driver 525+
#      GPU is exposed to WSL2 automatically — no extra config needed
#
# Then run this script INSIDE the WSL2 terminal:
#   chmod +x scripts/deploy/wsl2_setup.sh
#   ./scripts/deploy/wsl2_setup.sh
#
# NOTE: In this dev mode, LLM_BACKEND defaults to "openai" (no local SGLang).
#       SGLang can optionally be started if you have a GPU in WSL2.
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

# =============================================================================
section "Step 1 — Verify WSL2 environment"
# =============================================================================

# Confirm we are inside WSL2 (not native Linux or Windows CMD)
if ! grep -qi "microsoft\|wsl" /proc/version 2>/dev/null; then
  warn "This doesn't look like a WSL2 environment."
  warn "If you're on AutoDL (native Linux), use autodl_setup.sh instead."
  read -rp "Continue anyway? [y/N]: " CONT
  [[ "${CONT,,}" == "y" ]] || exit 1
fi

info "WSL2 kernel: $(uname -r)"
info "Distro: $(lsb_release -ds 2>/dev/null || echo 'unknown')"

# GPU check (optional in WSL2 dev mode)
HAS_GPU=false
if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
  GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
  info "GPU detected in WSL2: ${GPU_NAME}"
  HAS_GPU=true
else
  warn "No GPU detected in WSL2. LLM_BACKEND will default to 'openai'."
  warn "To enable GPU in WSL2: ensure Windows NVIDIA driver >= 525 is installed."
fi

# =============================================================================
section "Step 2 — Install dependencies"
# =============================================================================

# uv
if ! command -v uv &>/dev/null; then
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  # Add to shell profile
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  info "uv installed: $(uv --version)"
else
  info "uv: $(uv --version)"
fi

# Docker (via Docker Desktop WSL2 integration — preferred)
if ! command -v docker &>/dev/null; then
  error "Docker not found in WSL2. Please enable WSL2 integration in Docker Desktop:\n  Docker Desktop → Settings → Resources → WSL Integration → Enable for Ubuntu-22.04"
fi
info "Docker: $(docker --version)"

# Docker Compose
if ! docker compose version &>/dev/null; then
  error "Docker Compose not found. Ensure Docker Desktop is updated."
fi
info "Docker Compose: $(docker compose version --short)"

# Install Python workspace deps
info "Installing Python workspace dependencies..."
uv sync --all-packages

# =============================================================================
section "Step 3 — Configure environment for dev mode"
# =============================================================================

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  info "Created .env from .env.example"
fi

# Default to OpenAI API mode in WSL2 (no GPU = no local SGLang needed)
if [[ "$HAS_GPU" == "false" ]]; then
  sed -i "s|^LLM_BACKEND=.*|LLM_BACKEND=openai|" .env
  info "LLM_BACKEND set to 'openai' (no local GPU)"

  if ! grep -qE "^OPENAI_API_KEY=sk-" .env 2>/dev/null; then
    echo -n "Enter your OpenAI API key: "
    read -r OPENAI_KEY
    if [[ -n "$OPENAI_KEY" ]]; then
      sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${OPENAI_KEY}|" .env
      info "OPENAI_API_KEY set"
    else
      warn "No OpenAI key. Set OPENAI_API_KEY in .env before using /diagnose."
    fi
  fi
else
  # GPU available — offer SGLang option
  read -rp "Start SGLang local server? (requires ~16GB VRAM) [Y/n]: " USE_SGLANG
  USE_SGLANG="${USE_SGLANG:-Y}"
  if [[ "${USE_SGLANG^^}" == "Y" ]]; then
    sed -i "s|^LLM_BACKEND=.*|LLM_BACKEND=sglang|" .env
    info "LLM_BACKEND set to 'sglang'"
    # SGLang setup is the same as autodl — re-use that logic
    SGLANG_PORT="${SGLANG_PORT:-8100}"
    sed -i "s|^SGLANG_BASE_URL=.*|SGLANG_BASE_URL=http://localhost:${SGLANG_PORT}/v1|" .env
  else
    sed -i "s|^LLM_BACKEND=.*|LLM_BACKEND=openai|" .env
    info "LLM_BACKEND set to 'openai'"
  fi
fi

# WSL2-specific: fix Docker socket path if needed
if [[ ! -S /var/run/docker.sock ]]; then
  warn "Docker socket not found at /var/run/docker.sock"
  warn "Make sure Docker Desktop WSL2 integration is enabled."
fi

# =============================================================================
section "Step 4 — Start infrastructure"
# =============================================================================

COMPOSE_FILE="infra/compose/docker-compose.yml"

info "Starting MongoDB and Redis..."
docker compose -f "$COMPOSE_FILE" up mongo redis -d

info "Waiting for services..."
for i in {1..30}; do
  MONGO_OK=false
  REDIS_OK=false
  docker compose -f "$COMPOSE_FILE" exec -T mongo mongosh --eval "db.adminCommand('ping')" &>/dev/null && MONGO_OK=true
  docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping &>/dev/null && REDIS_OK=true
  [[ "$MONGO_OK" == "true" && "$REDIS_OK" == "true" ]] && break
  [[ $i -eq 30 ]] && error "Services failed to start"
  sleep 1
done
info "MongoDB and Redis ready"

# =============================================================================
section "Step 5 — Start FaultAtlas services (hot reload)"
# =============================================================================

echo ""
info "Start services with hot reload:"
echo ""
echo "  # Terminal 1 — API"
echo "  uv run --package faultatlas-api fastapi dev services/api/app/main.py --port 8000"
echo ""
echo "  # Terminal 2 — Retriever"
echo "  uv run --package faultatlas-retriever fastapi dev services/retriever/app/main.py --port 8001"
echo ""
echo "  # Terminal 3 — Ingestion worker (optional in dev)"
echo "  uv run --package faultatlas-ingestion python -m app.main"
echo ""
echo "  # Or run all in Docker:"
echo "  docker compose -f ${COMPOSE_FILE} up api retriever ingestion --build"
echo ""

read -rp "Start services in Docker now? [y/N]: " START_DOCKER
if [[ "${START_DOCKER,,}" == "y" ]]; then
  docker compose -f "$COMPOSE_FILE" up api retriever ingestion -d --build
  info "Services started. API: http://localhost:8000/docs"
fi

# =============================================================================
section "WSL2 dev setup complete"
# =============================================================================

echo ""
echo -e "${GREEN}FaultAtlas dev environment ready in WSL2.${NC}"
echo ""
echo "  API docs:    http://localhost:8000/docs  (after starting api service)"
echo "  Run tests:   uv run pytest"
echo "  Seed data:   uv run python scripts/seed_data.py"
echo "  Stop all:    ./scripts/deploy/stop.sh"
echo ""
echo "  Windows browser → WSL2 services: just use localhost:8000 (WSL2 port forwarding is automatic)"
echo ""
