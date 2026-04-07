from datetime import datetime

from pydantic import BaseModel, Field


class BenchmarkRunInput(BaseModel):
    condition: str
    run_index: int
    query: str
    ttft_ms: int | None = None
    total_latency_ms: int | None = None
    tokens_per_second: float | None = None
    prefix_cache_hint: str = "unknown"
    error: str | None = None


class BenchmarkConditionSummary(BaseModel):
    runs: int
    mean_ttft_ms: float
    p95_ttft_ms: float
    mean_tokens_per_sec: float
    error_count: int
    cold_start_accuracy: str | None = None


class BenchmarkHypothesisResult(BaseModel):
    shared_vs_cold_ratio: float
    hypothesis_met: bool
    verdict: str


class BenchmarkRunResponse(BaseModel):
    run_id: str
    backend: str
    model: str
    hardware: str
    conditions: dict[str, BenchmarkConditionSummary]
    hypothesis_result: BenchmarkHypothesisResult
    raw_runs: list[BenchmarkRunInput]
    created_at: datetime


class BenchmarkStoredRun(BenchmarkRunResponse):
    id: str = Field(alias="_id")

    model_config = {"populate_by_name": True}
