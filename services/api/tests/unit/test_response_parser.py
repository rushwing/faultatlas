import pytest

from services.api.app.agents.response_parser import parse_diagnosis_output
from services.api.app.llm.errors import LLMOutputParseError


def test_parse_diagnosis_output_from_code_fence() -> None:
    payload = """```json
{"summary":"oom","suspected_causes":["memory"],"evidence_chunk_ids":["chunk-1"],"next_actions":["restart"],"confidence":"medium"}
```"""
    parsed = parse_diagnosis_output(payload)
    assert parsed.summary == "oom"
    assert parsed.evidence_chunk_ids == ["chunk-1"]


def test_parse_diagnosis_output_raises_on_invalid_json() -> None:
    with pytest.raises(LLMOutputParseError):
        parse_diagnosis_output("not json")
