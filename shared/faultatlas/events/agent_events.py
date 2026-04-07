from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentRequested(BaseModel):
    """Published to: faultatlas.agent.requested"""

    event_type: str = "agent.requested"
    session_id: str
    query: str
    user_id: str
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    context: dict[str, Any] = Field(default_factory=dict)


class AgentCompleted(BaseModel):
    """Published to: faultatlas.agent.completed"""

    event_type: str = "agent.completed"
    session_id: str
    answer: str
    sources: list[str] = Field(default_factory=list)
    tokens_used: int
    latency_ms: int
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
