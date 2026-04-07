from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


class Collections:
    DOCUMENTS = "documents"
    CHUNKS = "chunks"
    INCIDENTS = "incidents"
    CITATIONS = "citations"
    BENCHMARK_RUNS = "benchmark_runs"
    AGENT_SESSIONS = "agent_sessions"
    AUDIT_LOG = "audit_log"


_client: AsyncIOMotorClient | None = None


def get_client(mongo_uri: str) -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(mongo_uri)
    return _client


def get_database(mongo_uri: str, db_name: str) -> AsyncIOMotorDatabase:
    return get_client(mongo_uri)[db_name]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
