import time
from typing import Any, cast

from openai import APIConnectionError, AsyncOpenAI, RateLimitError

from ...config import Settings
from ..client import LLMResponse
from ..errors import LLMBackendUnavailableError, LLMEmptyResponseError


class OpenAILLMClient:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_chat_model

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> LLMResponse:
        start = time.monotonic()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=cast(Any, messages),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (APIConnectionError, RateLimitError) as exc:
            raise LLMBackendUnavailableError("openai", str(exc)) from exc

        total_latency_ms = int((time.monotonic() - start) * 1000)
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise LLMEmptyResponseError("OpenAI returned an empty completion")

        output_tokens = 0
        if response.usage and response.usage.completion_tokens:
            output_tokens = response.usage.completion_tokens
        if output_tokens <= 0:
            output_tokens = max(len(content) // 4, 1)

        return LLMResponse(
            content=content,
            tokens_used=response.usage.total_tokens if response.usage else output_tokens,
            ttft_ms=max(total_latency_ms // max(output_tokens, 1), 1),
            total_latency_ms=total_latency_ms,
            prefix_cache_hint="unknown",
        )

    async def flush_cache(self) -> bool:
        return False
