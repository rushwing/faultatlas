import logging

import numpy as np
from faultatlas.embeddings import embed_text_locally, should_use_local_embeddings
from motor.motor_asyncio import AsyncIOMotorDatabase
from openai import AsyncOpenAI, RateLimitError

logger = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-10))


async def vector_search(
    query: str,
    db: AsyncIOMotorDatabase,
    openai_api_key: str,
    embedding_model: str,
    top_k: int = 5,
) -> list[dict]:
    """
    MVP: in-memory cosine similarity over all stored embeddings.
    Replace with MongoDB Atlas Vector Search $vectorSearch in production.
    """
    if top_k <= 0:
        return []

    if should_use_local_embeddings(openai_api_key):
        query_vector = embed_text_locally(query)
    else:
        client = AsyncOpenAI(api_key=openai_api_key)
        try:
            response = await client.embeddings.create(input=[query], model=embedding_model)
        except RateLimitError as exc:
            raise RuntimeError("embedding_unavailable") from exc
        query_vector = response.data[0].embedding

    cursor = db["chunks"].find(
        {"embedding": {"$exists": True}},
        {"content": 1, "document_id": 1, "embedding": 1},
    )
    results = []
    async for doc in cursor:
        score = cosine_similarity(query_vector, doc["embedding"])
        results.append(
            {
                "chunk_id": doc["_id"],
                "document_id": doc["document_id"],
                "content": doc["content"],
                "score": score,
            }
        )

    results.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    top = results[:top_k]
    logger.debug("vector search complete", extra={"top_k": top_k, "candidates": len(results)})
    return top
