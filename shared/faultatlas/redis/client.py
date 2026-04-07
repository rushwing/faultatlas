import redis.asyncio as aioredis


class RedisKeys:
    @staticmethod
    def session(session_id: str) -> str:
        return f"api:session:{session_id}"

    @staticmethod
    def query_cache(query_hash: str) -> str:
        return f"retriever:query_cache:{query_hash}"

    @staticmethod
    def rate_limit(user_id: str, bucket: str) -> str:
        return f"api:ratelimit:{user_id}:{bucket}"

    @staticmethod
    def idempotency(doc_hash: str) -> str:
        return f"ingestion:idempotency:{doc_hash}"

    @staticmethod
    def embed_lock(chunk_id: str) -> str:
        return f"ingestion:lock:embed:{chunk_id}"

    @staticmethod
    def doc_status(document_id: str) -> str:
        return f"ingestion:status:{document_id}"

    @staticmethod
    def notifications_channel(user_id: str) -> str:
        return f"faultatlas:notifications:{user_id}"


_redis: aioredis.Redis | None = None


def get_redis(redis_url: str) -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(redis_url, decode_responses=True)
    return _redis
