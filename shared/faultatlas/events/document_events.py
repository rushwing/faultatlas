from datetime import datetime, UTC
from typing import Any
from pydantic import BaseModel, Field


class DocumentUploaded(BaseModel):
    """Published to: faultatlas.documents.uploaded"""
    event_type: str = "document.uploaded"
    document_id: str
    filename: str
    content_type: str
    storage_path: str
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentIndexed(BaseModel):
    """Published to: faultatlas.index.updated"""
    event_type: str = "document.indexed"
    document_id: str
    chunk_count: int
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
