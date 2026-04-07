import logging

from fastapi import APIRouter
from pydantic import BaseModel

from ..dependencies import AuthDep, DBDep, RedisDep, SettingsDep
from .diagnose import DiagnosisRequest, diagnose

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
    logger.warning("/query is deprecated; use /diagnose instead")
    diagnosis = await diagnose(
        DiagnosisRequest(query=request.query, user_id=request.user_id),
        _,
        db,
        redis,
        settings,
    )
    return QueryResponse(
        session_id=diagnosis.session_id,
        answer=diagnosis.summary,
        sources=sorted({item.document_id for item in diagnosis.evidence}),
        tokens_used=diagnosis.tokens_used,
    )
