import os
import uuid
from datetime import UTC, datetime

import httpx
from faultatlas.mongo.client import Collections
from faultatlas.redis.client import RedisKeys
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from ..agents.prompt_builder import build_diagnosis_prompt
from ..agents.tools import retrieve_context
from ..config import Settings
from ..llm import get_llm_client
from ..llm.errors import LLMBackendUnavailableError
from ..schemas.benchmark import BenchmarkRunInput, BenchmarkRunResponse
from .metrics import summarize_condition
from .report import build_hypothesis_result

SHARED_PREFIX_QUERY = "Java OutOfMemoryError in payment-processor"
SHARED_PREFIX_VARIANTS = [
    "Investigate Java heap space failures in payment-processor",
    "Why is payment-processor crashing with heap exhaustion?",
    "What is the most likely cause of the repeated OOM in payment-processor?",
    "Give next actions for a Java heap space incident in payment-processor",
    "Summarize evidence for the payment-processor OutOfMemoryError",
]
NO_SHARED_VARIANTS = [
    "TCP timeout in order processing",
    "Circuit breaker opened on payment gateway",
    "Service restart loop with high memory",
    "Disk usage alert on database node",
    "Connection pool exhaustion in checkout service",
]


async def _ensure_backend_ready(settings: Settings) -> None:
    if settings.llm_backend != "sglang":
        return
    base_url = settings.sglang_base_url.rstrip("/")
    root_url = base_url[:-3] if base_url.endswith("/v1") else base_url
    health_url = root_url + "/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)
    except httpx.HTTPError as exc:
        raise LLMBackendUnavailableError("sglang", str(exc)) from exc
    if response.status_code >= 400:
        raise LLMBackendUnavailableError("sglang", response.text)


async def _run_prompt(
    *,
    llm_client,
    query: str,
    chunks: list[dict],
    condition: str,
    run_index: int,
    variant: str = "default",
) -> BenchmarkRunInput:
    prompt_bundle = build_diagnosis_prompt(query, chunks, variant=variant)
    try:
        response = await llm_client.complete(
            prompt_bundle.messages,
            max_tokens=800,
            temperature=0.1,
        )
    except Exception as exc:
        return BenchmarkRunInput(
            condition=condition,
            run_index=run_index,
            query=query,
            prefix_cache_hint="unknown",
            error=str(exc),
        )

    output_tokens = max(len(response.content) // 4, 1)
    tokens_per_second = output_tokens / max(response.total_latency_ms / 1000, 0.001)
    return BenchmarkRunInput(
        condition=condition,
        run_index=run_index,
        query=query,
        ttft_ms=response.ttft_ms,
        total_latency_ms=response.total_latency_ms,
        tokens_per_second=tokens_per_second,
        prefix_cache_hint=response.prefix_cache_hint or condition,
    )


async def run_benchmark(
    *,
    db: AsyncIOMotorDatabase,
    redis: Redis,
    settings: Settings,
    runs_per_condition: int = 5,
    backend_override: str | None = None,
) -> BenchmarkRunResponse:
    benchmark_settings = settings.model_copy(
        update={"llm_backend": backend_override} if backend_override else {}
    )
    await _ensure_backend_ready(benchmark_settings)

    llm_client = get_llm_client(benchmark_settings)
    run_id = str(uuid.uuid4())
    await redis.setex(RedisKeys.benchmark_run(run_id), 3600, "running")

    cold_start_accuracy = "best_effort"
    raw_runs: list[BenchmarkRunInput] = []
    shared_chunks = await retrieve_context(
        query=SHARED_PREFIX_QUERY,
        retriever_url=benchmark_settings.retriever_url,
        redis=redis,
    )

    cold_runs = []
    base_prompt_query = SHARED_PREFIX_VARIANTS[0]
    for run_index in range(runs_per_condition):
        flushed = await llm_client.flush_cache()
        if flushed:
            cold_start_accuracy = "flush_cache"
        run = await _run_prompt(
            llm_client=llm_client,
            query=base_prompt_query,
            chunks=shared_chunks,
            condition="cold_start",
            run_index=run_index,
        )
        cold_runs.append(run)
    raw_runs.extend(cold_runs)

    shared_runs = []
    for run_index, query in enumerate(SHARED_PREFIX_VARIANTS[:runs_per_condition]):
        run = await _run_prompt(
            llm_client=llm_client,
            query=query,
            chunks=shared_chunks,
            condition="shared_prefix",
            run_index=run_index,
        )
        shared_runs.append(run)
    raw_runs.extend(shared_runs)

    no_shared_runs = []
    for run_index, query in enumerate(NO_SHARED_VARIANTS[:runs_per_condition]):
        chunks = await retrieve_context(
            query=query,
            retriever_url=benchmark_settings.retriever_url,
            redis=redis,
        )
        run = await _run_prompt(
            llm_client=llm_client,
            query=query,
            chunks=chunks,
            condition="no_shared_prefix",
            run_index=run_index,
            variant="control",
        )
        no_shared_runs.append(run)
    raw_runs.extend(no_shared_runs)

    cold_summary = summarize_condition(cold_runs, cold_start_accuracy=cold_start_accuracy)
    shared_summary = summarize_condition(shared_runs)
    no_shared_summary = summarize_condition(no_shared_runs)
    hypothesis_result = build_hypothesis_result(cold_summary, shared_summary)

    report = BenchmarkRunResponse(
        run_id=run_id,
        backend=benchmark_settings.llm_backend,
        model=(
            benchmark_settings.openai_chat_model
            if benchmark_settings.llm_backend == "openai"
            else benchmark_settings.model_name
        ),
        hardware=os.getenv("FAULTATLAS_HARDWARE", "single-machine"),
        conditions={
            "cold_start": cold_summary,
            "shared_prefix": shared_summary,
            "no_shared_prefix": no_shared_summary,
        },
        hypothesis_result=hypothesis_result,
        raw_runs=raw_runs,
        created_at=datetime.now(UTC),
    )
    await db[Collections.BENCHMARK_RUNS].insert_one(
        {"_id": run_id, **report.model_dump(exclude={"run_id"})}
    )
    await redis.setex(RedisKeys.benchmark_run(run_id), 3600, "completed")
    return report
