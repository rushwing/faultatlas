import logging
import uuid

from fastapi import APIRouter, HTTPException
from faultatlas.mongo.client import Collections
from pydantic import BaseModel

from ..agents.orchestrator import run_agent
from ..agents.prompt_builder import build_diagnosis_prompt
from ..dependencies import AuthDep, DBDep, RedisDep, SettingsDep
from ..llm.errors import LLMBackendUnavailableError, LLMOutputParseError
from ..schemas.diagnosis import DiagnosisResponse

logger = logging.getLogger(__name__)
router = APIRouter()
debug_router = APIRouter()


class DiagnosisRequest(BaseModel):
    query: str
    user_id: str = "anonymous"


@router.post("", response_model=DiagnosisResponse)
async def diagnose(
    request: DiagnosisRequest,
    _: AuthDep,
    db: DBDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> DiagnosisResponse:
    query = request.query.strip()
    user_id = request.user_id
    estimated_tokens = max(len(query) // 4, 1)
    if estimated_tokens > settings.max_query_tokens:
        raise HTTPException(status_code=400, detail="query_too_long")

    session_id = str(uuid.uuid4())
    try:
        response, prompt_bundle = await run_agent(
            query=query,
            session_id=session_id,
            settings=settings,
            redis=redis,
        )
    except RuntimeError as exc:
        if str(exc) == "retriever_unavailable":
            raise HTTPException(status_code=503, detail="retriever_unavailable") from exc
        raise
    except LLMBackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail="llm_unavailable") from exc
    except LLMOutputParseError as exc:
        raise HTTPException(
            status_code=500,
            detail="llm_output_parse_error",
        ) from exc

    await db[Collections.AGENT_SESSIONS].insert_one(
        {
            "_id": session_id,
            "query": query,
            "user_id": user_id,
            "response": response.model_dump(),
            "prompt_version": prompt_bundle.prompt_version,
            "layer1_hash": prompt_bundle.layer1_hash,
            "layer2_hash": prompt_bundle.layer2_hash,
        }
    )
    if response.evidence:
        await db[Collections.CITATIONS].insert_one(
            {
                "_id": session_id,
                "session_id": session_id,
                "query": query,
                "chunk_ids": [item.chunk_id for item in response.evidence],
            }
        )
    return response


@router.get("/{session_id}", response_model=DiagnosisResponse)
async def get_diagnosis(session_id: str, _: AuthDep, db: DBDep) -> DiagnosisResponse:
    document = await db[Collections.AGENT_SESSIONS].find_one({"_id": session_id})
    if not document:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")
    return DiagnosisResponse.model_validate(document["response"])


@debug_router.get("/debug/prompt")
async def debug_prompt(query: str, _: AuthDep, settings: SettingsDep, redis: RedisDep) -> dict:
    if not settings.prompt_debug_enabled:
        raise HTTPException(status_code=404, detail="Prompt debug disabled")

    try:
        from ..agents.tools import retrieve_context

        chunks = await retrieve_context(
            query=query,
            retriever_url=settings.retriever_url,
            redis=redis,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="retriever_unavailable") from exc

    prompt_bundle = build_diagnosis_prompt(query, chunks)
    return {
        "prompt_version": prompt_bundle.prompt_version,
        "layer1_hash": prompt_bundle.layer1_hash,
        "layer2_hash": prompt_bundle.layer2_hash,
        "layer3_preview": prompt_bundle.layer3_text[:160],
        "chunk_ids": prompt_bundle.chunk_ids,
        "total_estimated_tokens": prompt_bundle.total_estimated_tokens,
    }
