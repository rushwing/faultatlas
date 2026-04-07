import logging
import time

import httpx
from redis.asyncio import Redis

from ..config import Settings
from ..llm import get_llm_client
from ..llm.errors import LLMOutputParseError
from ..schemas.diagnosis import DiagnosisEvidenceItem, DiagnosisResponse
from .prompt_builder import PromptBundle, build_diagnosis_prompt
from .prompts import REPAIR_PROMPT
from .response_parser import parse_diagnosis_output
from .tools import retrieve_context

logger = logging.getLogger(__name__)


def _build_evidence(
    chunks: list[dict],
    referenced_chunk_ids: list[str],
) -> list[DiagnosisEvidenceItem]:
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}
    ordered_ids = referenced_chunk_ids or [chunk["chunk_id"] for chunk in chunks[:3]]
    evidence = []
    for chunk_id in ordered_ids:
        chunk = chunk_map.get(chunk_id)
        if not chunk:
            continue
        evidence.append(DiagnosisEvidenceItem(**chunk))
    return evidence


async def _run_llm_with_repair(
    settings: Settings,
    prompt_bundle: PromptBundle,
) -> tuple[DiagnosisResponse | None, dict]:
    llm_client = get_llm_client(settings)
    llm_response = await llm_client.complete(
        prompt_bundle.messages,
        max_tokens=800,
        temperature=0.1,
    )
    try:
        parsed = parse_diagnosis_output(llm_response.content)
        return None, {"parsed": parsed, "llm_response": llm_response}
    except LLMOutputParseError:
        repair_messages = [
            prompt_bundle.messages[0],
            {
                "role": "user",
                "content": REPAIR_PROMPT.format(bad_output=llm_response.content),
            },
        ]
        repair_response = await llm_client.complete(
            repair_messages,
            max_tokens=800,
            temperature=0.0,
        )
        parsed = parse_diagnosis_output(repair_response.content)
        return None, {"parsed": parsed, "llm_response": repair_response}


async def run_agent(
    query: str,
    session_id: str,
    settings: Settings,
    redis: Redis,
) -> tuple[DiagnosisResponse, PromptBundle]:
    """Single-step RAG agent: retrieve → prompt build → diagnose."""
    start = time.monotonic()

    try:
        chunks = await retrieve_context(
            query=query,
            retriever_url=settings.retriever_url,
            redis=redis,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError("retriever_unavailable") from exc

    prompt_bundle = build_diagnosis_prompt(query, chunks)
    _, llm_result = await _run_llm_with_repair(settings, prompt_bundle)
    parsed = llm_result["parsed"]
    llm_response = llm_result["llm_response"]

    evidence = _build_evidence(chunks, parsed.evidence_chunk_ids)
    if not evidence and chunks:
        evidence = _build_evidence(chunks, [])

    confidence = parsed.confidence
    if not chunks:
        confidence = "low"

    latency_ms = int((time.monotonic() - start) * 1000)
    response = DiagnosisResponse(
        session_id=session_id,
        summary=parsed.summary,
        suspected_causes=parsed.suspected_causes,
        evidence=evidence,
        next_actions=parsed.next_actions,
        confidence=confidence,
        latency_ms=latency_ms,
        tokens_used=llm_response.tokens_used,
        prefix_cache_hint=llm_response.prefix_cache_hint,
    )
    logger.info(
        "agent completed",
        extra={
            "session_id": session_id,
            "tokens": response.tokens_used,
            "latency_ms": latency_ms,
            "prompt_version": prompt_bundle.prompt_version,
        },
    )
    return response, prompt_bundle
