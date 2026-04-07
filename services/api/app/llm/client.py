from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResponse:
    content: str
    tokens_used: int
    ttft_ms: int
    total_latency_ms: int
    prefix_cache_hint: str


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> LLMResponse: ...

    async def flush_cache(self) -> bool: ...
