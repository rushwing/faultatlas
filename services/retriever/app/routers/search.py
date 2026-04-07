import logging

from fastapi import APIRouter, Depends
from faultatlas.mongo.client import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..retrieval.context_builder import build_context
from ..retrieval.vector_search import vector_search

logger = logging.getLogger(__name__)
router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]


def get_db(settings: Settings = Depends(get_settings)) -> AsyncIOMotorDatabase:
    return get_database(settings.mongo_uri, settings.mongo_db)


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    settings: Settings = Depends(get_settings),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> SearchResponse:
    results = await vector_search(
        query=request.query,
        db=db,
        openai_api_key=settings.openai_api_key,
        embedding_model=settings.openai_embedding_model,
        top_k=request.top_k,
    )
    trimmed = build_context(results)
    return SearchResponse(results=[SearchResult(**r) for r in trimmed])
