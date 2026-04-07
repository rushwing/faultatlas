import logging
import uuid

from fastapi import APIRouter
from faultatlas.mongo.client import Collections
from pydantic import BaseModel

from ..agents.orchestrator import run_agent
from ..dependencies import AuthDep, DBDep, RedisDep, SettingsDep

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    user_id: str = "anonymous"


class QueryResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[str]
    tokens_used: int


@router.post("", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    _: AuthDep,
    db: DBDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> QueryResponse:
    session_id = str(uuid.uuid4())
    logger.info("agent query started", extra={"session_id": session_id, "user_id": request.user_id})

    result = await run_agent(
        query=request.query,
        session_id=session_id,
        settings=settings,
        redis=redis,
    )

    # Persist session
    await db[Collections.AGENT_SESSIONS].insert_one(
        {
            "_id": session_id,
            "user_id": request.user_id,
            "query": request.query,
            "answer": result["answer"],
            "sources": result["sources"],
            "tokens_used": result["tokens_used"],
        }
    )

    return QueryResponse(
        session_id=session_id,
        answer=result["answer"],
        sources=result["sources"],
        tokens_used=result["tokens_used"],
    )
