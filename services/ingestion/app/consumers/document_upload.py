import logging

from faultatlas.kafka.producer import KafkaProducer
from faultatlas.redis.client import RedisKeys
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from ..config import Settings
from ..processors.chunker import chunk_text
from ..processors.embedder import embed_chunks
from ..processors.extractor import extract_text
from ..producers.events import (
    publish_chunks_created,
    publish_embeddings_created,
    publish_index_updated,
)
from ..storage.mongo import save_chunks, update_document_status
from ..storage.vector import upsert_embeddings

logger = logging.getLogger(__name__)


async def handle_document_uploaded(
    payload: dict,
    db: AsyncIOMotorDatabase,
    redis: Redis,
    producer: KafkaProducer,
    settings: Settings,
) -> None:
    document_id = payload["document_id"]
    correlation_id = payload["correlation_id"]
    content_type = payload["content_type"]

    logger.info("processing document", extra={"document_id": document_id})
    await redis.setex(RedisKeys.doc_status(document_id), 3600, "chunking")
    await update_document_status(db, document_id, "chunking")

    # Fetch raw content — in a real system, read from object store (S3/GCS)
    # For MVP, content is stored in MongoDB on upload
    doc = await db["documents"].find_one({"_id": document_id}, {"raw_content": 1})
    raw_content = doc.get("raw_content", b"") if doc else b""

    text = extract_text(raw_content, content_type)
    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)

    chunk_ids = await save_chunks(db, document_id, chunks, settings.openai_embedding_model)
    publish_chunks_created(producer, document_id, chunk_ids, correlation_id)

    await redis.setex(RedisKeys.doc_status(document_id), 3600, "embedding")
    await update_document_status(db, document_id, "embedding")

    embeddings = await embed_chunks(
        chunks, settings.openai_embedding_model, settings.openai_api_key
    )
    await upsert_embeddings(db, chunk_ids, embeddings, settings.openai_embedding_model)
    publish_embeddings_created(
        producer, document_id, chunk_ids, settings.openai_embedding_model, correlation_id
    )

    await redis.setex(RedisKeys.doc_status(document_id), 3600, "indexed")
    await update_document_status(db, document_id, "indexed")
    publish_index_updated(producer, document_id, len(chunk_ids), correlation_id)

    logger.info("document indexed", extra={"document_id": document_id, "chunks": len(chunk_ids)})
