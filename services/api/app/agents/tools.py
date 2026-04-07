import logging

import httpx
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


async def retrieve_context(
    query: str,
    retriever_url: str,
    redis: Redis,
    top_k: int = 5,
) -> list[dict]:
    """Call retriever service for relevant chunks."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{retriever_url}/search",
            json={"query": query, "top_k": top_k},
        )
        response.raise_for_status()
        results = response.json()["results"]
        return results
