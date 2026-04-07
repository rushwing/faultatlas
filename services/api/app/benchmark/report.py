from ..schemas.benchmark import BenchmarkConditionSummary, BenchmarkHypothesisResult


def build_hypothesis_result(
    cold_start: BenchmarkConditionSummary,
    shared_prefix: BenchmarkConditionSummary,
) -> BenchmarkHypothesisResult:
    if cold_start.mean_ttft_ms <= 0:
        ratio = 0.0
    else:
        ratio = shared_prefix.mean_ttft_ms / cold_start.mean_ttft_ms
    hypothesis_met = cold_start.mean_ttft_ms > 0 and ratio <= 0.60
    verdict = (
        f"Shared-prefix TTFT ({shared_prefix.mean_ttft_ms:.1f}ms) is "
        f"{ratio:.2%} of cold-start TTFT ({cold_start.mean_ttft_ms:.1f}ms). "
        f"Hypothesis {'MET' if hypothesis_met else 'NOT MET'}."
    )
    return BenchmarkHypothesisResult(
        shared_vs_cold_ratio=ratio,
        hypothesis_met=hypothesis_met,
        verdict=verdict,
    )
