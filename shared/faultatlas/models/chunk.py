from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    id: str = Field(alias="_id")
    document_id: str
    content: str
    chunk_index: int
    token_count: int
    embedding_model: str | None = None
    vector_store_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"populate_by_name": True}
