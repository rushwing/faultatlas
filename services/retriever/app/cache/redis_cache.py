import hashlib
import json

from faultatlas.redis.client import RedisKeys
from redis.asyncio import Redis


def build_query_cache_key(query: str, top_k: int) -> str:
    query_hash = hashlib.md5(f"{query}:{top_k}".encode()).hexdigest()
    return RedisKeys.query_cache(query_hash)


async def get_cached_results(redis: Redis, query: str, top_k: int) -> list[dict] | None:
    payload = await redis.get(build_query_cache_key(query, top_k))
    if not payload:
        return None
    return json.loads(payload)


async def set_cached_results(redis: Redis, query: str, top_k: int, results: list[dict]) -> None:
    if not results:
        return
    await redis.setex(build_query_cache_key(query, top_k), 300, json.dumps(results))
