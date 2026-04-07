import uuid
import logging
from datetime import datetime, UTC
from motor.motor_asyncio import AsyncIOMotorDatabase

from faultatlas.mongo.client import Collections

logger = logging.getLogger(__name__)


async def save_chunks(
    db: AsyncIOMotorDatabase,
    document_id: str,
    texts: list[str],
    embedding_model: str,
) -> list[str]:
    chunk_ids = []
    now = datetime.now(UTC)
    docs = []
    for i, text in enumerate(texts):
        chunk_id = str(uuid.uuid4())
        chunk_ids.append(chunk_id)
        docs.append({
            "_id": chunk_id,
            "document_id": document_id,
            "content": text,
            "chunk_index": i,
            "token_count": len(text.split()),
            "embedding_model": embedding_model,
            "created_at": now,
        })
    await db[Collections.CHUNKS].insert_many(docs)
    logger.info("chunks saved", extra={"document_id": document_id, "count": len(docs)})
    return chunk_ids


async def update_document_status(db: AsyncIOMotorDatabase, document_id: str, status: str) -> None:
    await db[Collections.DOCUMENTS].update_one(
        {"_id": document_id},
        {"$set": {"status": status}},
    )
