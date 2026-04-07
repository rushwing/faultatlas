import importlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

compare_to_baseline = importlib.import_module(
    "harness.evals.prompt.eval_prompt_stability"
).compare_to_baseline


def test_compare_to_baseline_skips_placeholder_baseline(tmp_path) -> None:
    baseline_path = tmp_path / "prompt_baseline_v1.json"
    baseline_path.write_text(
        json.dumps(
            {
                "placeholder": True,
                "version": "v1",
                "faithfulness": 0.0,
            }
        )
    )

    result = compare_to_baseline({"faithfulness": 0.8}, baseline_path)

    assert result["passed"] is True
    assert result["skipped"] is True
    assert "placeholder" in result["verdict"].lower()
