import json
import re

from pydantic import ValidationError

from ..llm.errors import LLMOutputParseError
from ..schemas.diagnosis import DiagnosisLLMOutput

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_tags(content: str) -> str:
    return _THINK_RE.sub("", content).strip()


def _extract_json_block(content: str) -> str:
    fenced = _CODE_FENCE_RE.search(content)
    if fenced:
        return fenced.group(1).strip()

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise LLMOutputParseError("No JSON object found in LLM output", content)
    return content[start : end + 1]


def parse_diagnosis_output(content: str) -> DiagnosisLLMOutput:
    content = _strip_think_tags(content)
    json_block = _extract_json_block(content)
    try:
        payload = json.loads(json_block)
    except json.JSONDecodeError as exc:
        raise LLMOutputParseError("Invalid JSON in LLM output", content) from exc

    evidence_chunk_ids = payload.get("evidence_chunk_ids")
    if evidence_chunk_ids is None and isinstance(payload.get("evidence"), list):
        evidence_chunk_ids = []
        for item in payload["evidence"]:
            if isinstance(item, dict) and item.get("chunk_id"):
                evidence_chunk_ids.append(item["chunk_id"])

    normalized = {
        "summary": str(payload.get("summary", "")).strip(),
        "suspected_causes": [str(item).strip() for item in payload.get("suspected_causes", [])],
        "evidence_chunk_ids": [str(item).strip() for item in (evidence_chunk_ids or [])],
        "next_actions": [str(item).strip() for item in payload.get("next_actions", [])],
        "confidence": str(payload.get("confidence", "low")).strip().lower(),
    }
    try:
        return DiagnosisLLMOutput.model_validate(normalized)
    except ValidationError as exc:
        raise LLMOutputParseError("Diagnosis output failed schema validation", content) from exc
