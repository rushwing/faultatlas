import io
import logging
from datetime import UTC, datetime
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from motor.motor_asyncio import AsyncIOMotorDatabase
from openai import AsyncOpenAI, RateLimitError
from pypdf import PdfReader
from redis.asyncio import Redis

from .embeddings import embed_text_locally, should_use_local_embeddings
from .mongo.client import Collections
from .redis.client import RedisKeys

logger = logging.getLogger(__name__)


def extract_text(content: bytes, content_type: str) -> tuple[str, dict[str, Any]]:
    if content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("encrypted_pdf")

        unreadable_pages: list[int] = []
        pages: list[str] = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if not text.strip():
                unreadable_pages.append(index)
            pages.append(text)

        return "\n".join(pages), {"unreadable_pages": unreadable_pages}

    return content.decode("utf-8", errors="replace"), {"unreadable_pages": []}


def chunk_text(text: str, chunk_size: int = 512, chunk_overlap: int = 64) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    return splitter.split_text(text)


async def embed_chunks(chunks: list[str], model: str, api_key: str) -> list[list[float]]:
    if should_use_local_embeddings(api_key):
        return [embed_text_locally(chunk) for chunk in chunks]

    client = AsyncOpenAI(api_key=api_key)
    all_embeddings: list[list[float]] = []
    batch_size = 100
    for index in range(0, len(chunks), batch_size):
        batch = chunks[index : index + batch_size]
        try:
            response = await client.embeddings.create(input=batch, model=model)
        except RateLimitError as exc:
            raise RuntimeError("embedding_api_unavailable") from exc
        all_embeddings.extend([row.embedding for row in response.data])
        logger.debug("embedded batch", extra={"batch": index // batch_size, "count": len(batch)})
    return all_embeddings


async def save_chunks(
    db: AsyncIOMotorDatabase,
    document_id: str,
    texts: list[str],
    embedding_model: str,
) -> list[str]:
    import uuid

    chunk_ids = []
    now = datetime.now(UTC)
    docs = []
    for i, text in enumerate(texts):
        chunk_id = str(uuid.uuid4())
        chunk_ids.append(chunk_id)
        docs.append(
            {
                "_id": chunk_id,
                "document_id": document_id,
                "content": text,
                "chunk_index": i,
                "token_count": len(text.split()),
                "embedding_model": embedding_model,
                "created_at": now,
            }
        )

    if docs:
        await db[Collections.CHUNKS].insert_many(docs)
    logger.info("chunks saved", extra={"document_id": document_id, "count": len(docs)})
    return chunk_ids


async def upsert_embeddings(
    db: AsyncIOMotorDatabase,
    chunk_ids: list[str],
    embeddings: list[list[float]],
    model: str,
) -> None:
    for chunk_id, vector in zip(chunk_ids, embeddings):
        await db[Collections.CHUNKS].update_one(
            {"_id": chunk_id},
            {"$set": {"embedding": vector, "embedding_model": model}},
        )
    logger.info("embeddings upserted", extra={"count": len(chunk_ids), "model": model})


async def update_document_fields(db: AsyncIOMotorDatabase, document_id: str, fields: dict) -> None:
    await db[Collections.DOCUMENTS].update_one({"_id": document_id}, {"$set": fields})


async def ingest_document(
    *,
    document_id: str,
    filename: str,
    content_type: str,
    content: bytes,
    db: AsyncIOMotorDatabase,
    redis: Redis,
    openai_api_key: str,
    embedding_model: str,
    chunk_size: int,
    chunk_overlap: int,
) -> dict[str, Any]:
    await db[Collections.DOCUMENTS].insert_one(
        {
            "_id": document_id,
            "filename": filename,
            "content_type": content_type,
            "status": "pending",
            "source_metadata": {"size_bytes": len(content)},
            "created_at": datetime.now(UTC),
        }
    )
    await redis.setex(RedisKeys.doc_status(document_id), 3600, "pending")

    try:
        await redis.setex(RedisKeys.doc_status(document_id), 3600, "chunking")
        await update_document_fields(db, document_id, {"status": "chunking"})

        text, source_metadata = extract_text(content, content_type)
        chunks = chunk_text(text, chunk_size, chunk_overlap)
        chunk_ids = await save_chunks(db, document_id, chunks, embedding_model)

        await redis.setex(RedisKeys.doc_status(document_id), 3600, "embedding")
        await update_document_fields(db, document_id, {"status": "embedding"})

        embeddings = await embed_chunks(chunks, embedding_model, openai_api_key)
        await upsert_embeddings(db, chunk_ids, embeddings, embedding_model)

        await redis.setex(RedisKeys.doc_status(document_id), 3600, "indexed")
        await update_document_fields(
            db,
            document_id,
            {
                "status": "indexed",
                "chunk_count": len(chunk_ids),
                "source_metadata": {
                    "size_bytes": len(content),
                    **source_metadata,
                },
            },
        )
    except Exception as exc:
        error_detail = str(exc)
        await redis.setex(RedisKeys.doc_status(document_id), 3600, "failed")
        await update_document_fields(
            db,
            document_id,
            {"status": "failed", "error_detail": error_detail},
        )
        logger.exception("document ingestion failed", extra={"document_id": document_id})
        raise

    return {
        "document_id": document_id,
        "status": "indexed",
        "chunk_count": len(chunk_ids),
    }
