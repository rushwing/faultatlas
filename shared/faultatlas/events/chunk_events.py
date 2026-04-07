from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ChunksCreated(BaseModel):
    """Published to: faultatlas.chunks.created"""

    event_type: str = "chunks.created"
    document_id: str
    chunk_ids: list[str]
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EmbeddingsCreated(BaseModel):
    """Published to: faultatlas.embeddings.created"""

    event_type: str = "embeddings.created"
    document_id: str
    chunk_ids: list[str]
    embedding_model: str
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
