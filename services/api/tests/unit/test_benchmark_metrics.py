from services.api.app.benchmark.metrics import summarize_condition
from services.api.app.benchmark.report import build_hypothesis_result
from services.api.app.schemas.benchmark import BenchmarkRunInput


def test_benchmark_metrics_and_report() -> None:
    cold_runs = [
        BenchmarkRunInput(
            condition="cold_start",
            run_index=0,
            query="q",
            ttft_ms=100,
            total_latency_ms=200,
            tokens_per_second=10.0,
        ),
        BenchmarkRunInput(
            condition="cold_start",
            run_index=1,
            query="q",
            ttft_ms=120,
            total_latency_ms=220,
            tokens_per_second=9.0,
        ),
    ]
    shared_runs = [
        BenchmarkRunInput(
            condition="shared_prefix",
            run_index=0,
            query="q",
            ttft_ms=40,
            total_latency_ms=90,
            tokens_per_second=20.0,
        ),
    ]
    cold_summary = summarize_condition(cold_runs, cold_start_accuracy="best_effort")
    shared_summary = summarize_condition(shared_runs)
    report = build_hypothesis_result(cold_summary, shared_summary)
    assert cold_summary.error_count == 0
    assert report.shared_vs_cold_ratio > 0
    assert "Shared-prefix TTFT" in report.verdict
