import logging

from faultatlas.ingestion import ingest_document as run_shared_ingestion
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from ..config import Settings

logger = logging.getLogger(__name__)


async def ingest_document(
    *,
    document_id: str,
    filename: str,
    content_type: str,
    content: bytes,
    db: AsyncIOMotorDatabase,
    redis: Redis,
    settings: Settings,
) -> dict:
    logger.info("processing document", extra={"document_id": document_id})
    return await run_shared_ingestion(
        document_id=document_id,
        filename=filename,
        content_type=content_type,
        content=content,
        db=db,
        redis=redis,
        openai_api_key=settings.openai_api_key,
        embedding_model=settings.openai_embedding_model,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
