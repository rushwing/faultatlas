import statistics

from ..schemas.benchmark import BenchmarkConditionSummary, BenchmarkRunInput


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[index]


def summarize_condition(
    raw_runs: list[BenchmarkRunInput],
    *,
    cold_start_accuracy: str | None = None,
) -> BenchmarkConditionSummary:
    success_runs = [run for run in raw_runs if run.error is None and run.ttft_ms is not None]
    ttft_values = [float(run.ttft_ms) for run in success_runs if run.ttft_ms is not None]
    tps_values = [
        float(run.tokens_per_second) for run in success_runs if run.tokens_per_second is not None
    ]

    return BenchmarkConditionSummary(
        runs=len(raw_runs),
        mean_ttft_ms=statistics.fmean(ttft_values) if ttft_values else 0.0,
        p95_ttft_ms=_percentile(ttft_values, 0.95),
        mean_tokens_per_sec=statistics.fmean(tps_values) if tps_values else 0.0,
        error_count=sum(1 for run in raw_runs if run.error),
        cold_start_accuracy=cold_start_accuracy,
    )
