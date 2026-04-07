import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

from faultatlas.mongo.client import Collections

logger = logging.getLogger(__name__)


async def upsert_embeddings(
    db: AsyncIOMotorDatabase,
    chunk_ids: list[str],
    embeddings: list[list[float]],
    model: str,
) -> None:
    """Store embeddings alongside chunk records.

    For MVP we store vectors in MongoDB directly.
    Replace with MongoDB Atlas Vector Search or a dedicated vector DB in production.
    """
    for chunk_id, vector in zip(chunk_ids, embeddings):
        await db[Collections.CHUNKS].update_one(
            {"_id": chunk_id},
            {"$set": {"embedding": vector, "embedding_model": model}},
        )
    logger.info("embeddings upserted", extra={"count": len(chunk_ids), "model": model})
