from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    PENDING = "pending"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"


class Document(BaseModel):
    id: str = Field(alias="_id")
    filename: str
    content_type: str
    upload_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: DocumentStatus = DocumentStatus.PENDING
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    ingestion_job_id: str | None = None
    tags: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
