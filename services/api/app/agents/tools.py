import hashlib
import logging
import httpx
from redis.asyncio import Redis

from faultatlas.redis.client import RedisKeys

logger = logging.getLogger(__name__)


async def retrieve_context(
    query: str,
    retriever_url: str,
    redis: Redis,
    top_k: int = 5,
) -> list[dict]:
    """Call retriever service for relevant chunks. Caches results in Redis."""
    query_hash = hashlib.md5(f"{query}:{top_k}".encode()).hexdigest()
    cache_key = RedisKeys.query_cache(query_hash)

    cached = await redis.get(cache_key)
    if cached:
        import json
        logger.debug("retriever cache hit", extra={"query_hash": query_hash})
        return json.loads(cached)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{retriever_url}/search",
            json={"query": query, "top_k": top_k},
        )
        response.raise_for_status()
        results = response.json()["results"]

    import json
    await redis.setex(cache_key, 300, json.dumps(results))
    return results
