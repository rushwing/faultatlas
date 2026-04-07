---
req_id: REQ-013
title: Multi-GPU SGLang configuration
status: draft
phase: phase-3
milestone: M3.4
priority: P2
depends_on: [REQ-005]
owner: danielwong
---

# User Story

As a performance engineer scaling FaultAtlas beyond a single 4090, I want SGLang to run with tensor parallelism across multiple GPUs, and I want the benchmark to compare single-GPU vs. multi-GPU TTFT and throughput, so I can quantify the scaling benefit and recommend hardware configurations for production.

# Goal

Configure SGLang tensor parallelism (`--tensor-parallel-size N`) and run a comparative benchmark against the Phase 1 single-GPU baseline. This story is about measurement and documentation, not just configuration.

# AI Behavior Definition

No AI behavior — inference infrastructure configuration.

# Deliverables

- [ ] `scripts/deploy/sglang_server.sh` — add `--tensor-parallel-size` parameter
- [ ] `infra/env/.env.autodl-multi-gpu` — multi-GPU env template
- [ ] `POST /benchmark/run` — add `gpu_count` field to report
- [ ] `docs/benchmark_phase3_multigpu.md` — comparative report
- [ ] Verify prefix caching still functions with tensor parallelism (RadixAttention + TP compatibility)

# Acceptance Criteria

1. SGLang starts with `--tensor-parallel-size 2` on a 2x4090 node without errors
2. Multi-GPU throughput (tokens/s) ≥ 1.7× single-GPU (linear scaling is 2×; 85% efficiency is acceptable)
3. Prefix cache hit rate is unchanged between single-GPU and multi-GPU runs (same prompt, same KV cache behavior)
4. `benchmark_runs` report includes `gpu_count` and `tensor_parallel_size` fields

# Eval Design

```bash
# Single GPU baseline (from Phase 1)
TENSOR_PARALLEL_SIZE=1 ./scripts/deploy/sglang_server.sh start
uv run python scripts/run_benchmark.py --backend sglang > single_gpu.json

# Multi-GPU
TENSOR_PARALLEL_SIZE=2 ./scripts/deploy/sglang_server.sh start
uv run python scripts/run_benchmark.py --backend sglang > multi_gpu.json

python scripts/compare_benchmarks.py single_gpu.json multi_gpu.json
```

# Model / Data Dependencies

- Requires 2+ GPU instance on AutoDL (upgrade from single 4090)
- SGLang tensor parallelism requires NCCL; verify AutoDL instance has NVLink or PCIe bandwidth

# Out of Scope

- Pipeline parallelism
- Speculative decoding
- Multi-node distributed serving

# Notes for CodeX Review

- Check: SGLang TP + RadixAttention interaction — confirm prefix cache is maintained per-GPU or globally in TP mode (check SGLang release notes for the version in use)
