import pytest
from app.cache.redis_cache import get_cached_results, set_cached_results


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value


@pytest.mark.asyncio
async def test_set_cached_results_skips_empty_payloads() -> None:
    redis = FakeRedis()

    await set_cached_results(redis, "heap space", 5, [])

    assert await get_cached_results(redis, "heap space", 5) is None


@pytest.mark.asyncio
async def test_set_cached_results_persists_non_empty_payloads() -> None:
    redis = FakeRedis()
    results = [{"chunk_id": "chunk-1", "document_id": "doc-1", "content": "oom", "score": 0.9}]

    await set_cached_results(redis, "heap space", 5, results)

    assert await get_cached_results(redis, "heap space", 5) == results
