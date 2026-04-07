import logging

from fastapi import APIRouter, Depends, HTTPException
from faultatlas.mongo.client import get_database
from faultatlas.redis.client import get_redis
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from redis.asyncio import Redis

from ..cache.redis_cache import get_cached_results, set_cached_results
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


def get_redis_client(settings: Settings = Depends(get_settings)) -> Redis:
    return get_redis(settings.redis_url)


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    settings: Settings = Depends(get_settings),
    db: AsyncIOMotorDatabase = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> SearchResponse:
    if request.top_k <= 0:
        return SearchResponse(results=[])

    cached = await get_cached_results(redis, request.query, request.top_k)
    if cached is not None:
        trimmed = build_context(cached)
        return SearchResponse(results=[SearchResult(**r) for r in trimmed])

    try:
        results = await vector_search(
            query=request.query,
            db=db,
            openai_api_key=settings.openai_api_key,
            embedding_model=settings.openai_embedding_model,
            top_k=request.top_k,
        )
    except RuntimeError as exc:
        if str(exc) == "embedding_unavailable":
            raise HTTPException(status_code=503, detail="embedding_unavailable") from exc
        raise

    await set_cached_results(redis, request.query, request.top_k, results)
    trimmed = build_context(results)
    return SearchResponse(results=[SearchResult(**r) for r in trimmed])
