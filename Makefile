# FaultAtlas — Development Makefile
# Usage: make <target>
#
# Targets are grouped by context:
#   local-*    : runs directly on host (uv, no Docker for app services)
#   docker-*   : runs everything in Docker
#   autodl-*   : AutoDL-specific (SGLang management)
#   test-*     : testing
#   infra-*    : infrastructure only

COMPOSE      := docker compose -f infra/compose/docker-compose.yml
COMPOSE_OBS  := $(COMPOSE) -f infra/compose/docker-compose.obs.yml
SGLANG       := ./scripts/deploy/sglang_server.sh

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2}'

# ── Bootstrap ────────────────────────────────────────────────────────────────

.PHONY: install
install:  ## Install all Python dependencies via uv
	uv sync --all-packages

.PHONY: setup-autodl
setup-autodl:  ## Full AutoDL setup (GPU verify, model download, start everything)
	chmod +x scripts/deploy/autodl_setup.sh
	./scripts/deploy/autodl_setup.sh

.PHONY: setup-wsl2
setup-wsl2:  ## WSL2 local dev setup
	chmod +x scripts/deploy/wsl2_setup.sh
	./scripts/deploy/wsl2_setup.sh

# ── Infrastructure ────────────────────────────────────────────────────────────

.PHONY: infra-up
infra-up:  ## Start MongoDB + Redis only
	$(COMPOSE) up mongo redis -d

.PHONY: infra-down
infra-down:  ## Stop MongoDB + Redis
	$(COMPOSE) stop mongo redis

.PHONY: infra-obs
infra-obs:  ## Start observability stack (Prometheus + Grafana + Loki)
	$(COMPOSE_OBS) up prometheus grafana loki promtail -d

# ── SGLang server (AutoDL) ────────────────────────────────────────────────────

.PHONY: sglang-start
sglang-start:  ## Start SGLang model server
	$(SGLANG) start

.PHONY: sglang-stop
sglang-stop:  ## Stop SGLang model server
	$(SGLANG) stop

.PHONY: sglang-status
sglang-status:  ## Show SGLang server status + GPU memory
	$(SGLANG) status

.PHONY: sglang-logs
sglang-logs:  ## Tail SGLang server logs
	$(SGLANG) logs

.PHONY: sglang-restart
sglang-restart:  ## Restart SGLang server
	$(SGLANG) restart

# ── Local development (hot reload, no Docker for app services) ────────────────

.PHONY: local-api
local-api:  ## Start API service with hot reload
	uv run --package faultatlas-api fastapi dev services/api/app/main.py --port 8000

.PHONY: local-retriever
local-retriever:  ## Start retriever service with hot reload
	uv run --package faultatlas-retriever fastapi dev services/retriever/app/main.py --port 8001

.PHONY: local-ingestion
local-ingestion:  ## Start ingestion worker
	uv run --package faultatlas-ingestion python -m app.main

# ── Docker (full stack in containers) ────────────────────────────────────────

.PHONY: docker-up
docker-up:  ## Start all services in Docker (build if needed)
	$(COMPOSE) up --build -d

.PHONY: docker-down
docker-down:  ## Stop all Docker services
	$(COMPOSE) down

.PHONY: docker-logs
docker-logs:  ## Tail all Docker service logs
	$(COMPOSE) logs -f

.PHONY: docker-rebuild
docker-rebuild:  ## Force rebuild all service images
	$(COMPOSE) build --no-cache

# ── Data ─────────────────────────────────────────────────────────────────────

.PHONY: seed
seed:  ## Upload sample runbooks + logs to knowledge base
	uv run python scripts/seed_data.py

.PHONY: reset
reset:  ## Wipe all volumes and restart clean
	./scripts/reset_dev.sh

# ── Testing ───────────────────────────────────────────────────────────────────

.PHONY: test
test:  ## Run all tests
	uv run pytest -v

.PHONY: test-unit
test-unit:  ## Run unit tests only
	uv run pytest -v -m "not integration"

.PHONY: test-api
test-api:  ## Run API service tests
	uv run pytest services/api/tests/ -v

.PHONY: test-ingestion
test-ingestion:  ## Run ingestion service tests
	uv run pytest services/ingestion/tests/ -v

.PHONY: test-retriever
test-retriever:  ## Run retriever service tests
	uv run pytest services/retriever/tests/ -v

.PHONY: smoke
smoke:  ## Run smoke test (curl-based end-to-end)
	./scripts/smoke_test.sh

.PHONY: benchmark
benchmark:  ## Run prefix caching benchmark
	curl -sf -X POST http://localhost:8000/benchmark/run \
	  -H "X-API-Key: $$(grep '^API_KEY=' .env | cut -d= -f2)" | python3 -m json.tool

# ── Eval harness (AI quality) ─────────────────────────────────────────────────
# Requires: services running (make infra-up + make local-api + make local-retriever)
# Distinct from tests/ — these score AI output quality, not software correctness.

.PHONY: eval
eval: eval-rag eval-agent eval-prompt  ## Run full eval suite (all 3 dimensions)

.PHONY: eval-smoke
eval-smoke:  ## Fast PR-safe smoke eval (diagnose schema + prompt stability)
	uv run --package faultatlas-harness python harness/evals/smoke/eval_diagnose_smoke.py
	uv run --package faultatlas-harness python harness/evals/smoke/eval_prompt_smoke.py

.PHONY: eval-rag
eval-rag:  ## RAG quality eval (faithfulness, context precision, recall, answer relevance)
	uv run --package faultatlas-harness python harness/evals/rag/eval_retrieval.py

.PHONY: eval-agent
eval-agent:  ## Agent/diagnosis quality eval (hallucination, schema, confidence calibration)
	uv run --package faultatlas-harness python harness/evals/agent/eval_diagnosis.py

.PHONY: eval-prompt
eval-prompt:  ## Prompt stability check (Layer 1 hash consistency)
	uv run --package faultatlas-harness python harness/evals/prompt/eval_prompt_stability.py --mode stability

.PHONY: eval-prompt-regression
eval-prompt-regression:  ## Prompt regression vs saved baseline (run after any prompts.py change)
	uv run --package faultatlas-harness python harness/evals/prompt/eval_prompt_stability.py \
	  --mode regression --baseline harness/reports/prompt_baseline_v1.json

.PHONY: eval-prompt-baseline
eval-prompt-baseline:  ## Save current prompt performance as baseline
	uv run --package faultatlas-harness python harness/evals/prompt/eval_prompt_stability.py \
	  --mode save-baseline --version v1

.PHONY: eval-model
eval-model:  ## Model comparison eval (requires GPU + multiple model servers)
	uv run --package faultatlas-harness python harness/evals/model/eval_model_comparison.py

# ── Code quality ──────────────────────────────────────────────────────────────

.PHONY: lint
lint:  ## Run ruff linter
	uv run ruff check .

.PHONY: format
format:  ## Auto-format with ruff
	uv run ruff format .

.PHONY: typecheck
typecheck:  ## Run mypy type checker
	uv run mypy services/ shared/

.PHONY: check
check: lint typecheck  ## Run all code quality checks

# ── Convenience ───────────────────────────────────────────────────────────────

.PHONY: status
status:  ## Show status of all services
	@echo "=== Docker services ==="
	@$(COMPOSE) ps 2>/dev/null || echo "  (docker compose not started)"
	@echo ""
	@echo "=== SGLang server ==="
	@$(SGLANG) status 2>/dev/null || echo "  (sglang_server.sh not found)"
	@echo ""
	@echo "=== API health ==="
	@curl -sf http://localhost:8000/health 2>/dev/null | python3 -m json.tool || echo "  API not reachable"
