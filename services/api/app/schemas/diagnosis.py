from typing import Literal

from pydantic import BaseModel, Field

ConfidenceLevel = Literal["low", "medium", "high"]


class DiagnosisEvidenceItem(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float


class DiagnosisLLMOutput(BaseModel):
    summary: str
    suspected_causes: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel


class DiagnosisResponse(BaseModel):
    session_id: str
    summary: str
    suspected_causes: list[str]
    evidence: list[DiagnosisEvidenceItem]
    next_actions: list[str]
    confidence: ConfidenceLevel
    latency_ms: int
    tokens_used: int
    prefix_cache_hint: str


class DiagnosisSessionRecord(BaseModel):
    id: str = Field(alias="_id")
    query: str
    user_id: str
    response: DiagnosisResponse
    prompt_version: str
    layer1_hash: str
    layer2_hash: str

    model_config = {"populate_by_name": True}
