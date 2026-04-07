import time

import httpx

from ...config import Settings
from ..client import LLMResponse
from ..errors import LLMBackendUnavailableError, LLMEmptyResponseError


def _normalize_prefix_cache_hint(value: str | None) -> str:
    if not value:
        return "unknown"
    normalized = value.strip().lower()
    if normalized in {"true", "1", "hit", "shared"}:
        return "shared"
    if normalized in {"false", "0", "miss", "cold"}:
        return "cold"
    if normalized in {"no_shared", "no-shared"}:
        return "no_shared"
    return "unknown"


class SGLangLLMClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.sglang_base_url.rstrip("/")
        self._model = settings.model_name

    @property
    def _root_url(self) -> str:
        return self._base_url[:-3] if self._base_url.endswith("/v1") else self._base_url

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{self._base_url}/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMBackendUnavailableError("sglang", str(exc)) from exc

        if response.status_code >= 500:
            raise LLMBackendUnavailableError("sglang", response.text)

        response.raise_for_status()
        total_latency_ms = int((time.monotonic() - start) * 1000)
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if not content.strip():
            raise LLMEmptyResponseError("SGLang returned an empty completion")

        usage = data.get("usage", {})
        output_tokens = usage.get("completion_tokens") or max(len(content) // 4, 1)
        return LLMResponse(
            content=content,
            tokens_used=usage.get("total_tokens", output_tokens),
            ttft_ms=max(total_latency_ms // max(output_tokens, 1), 1),
            total_latency_ms=total_latency_ms,
            prefix_cache_hint=_normalize_prefix_cache_hint(
                response.headers.get("x-prefix-cache-hit")
            ),
        )

    async def flush_cache(self) -> bool:
        for path in ("/flush_cache", "/v1/flush_cache"):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(f"{self._root_url}{path}")
            except httpx.HTTPError:
                continue
            if response.status_code < 400:
                return True
        return False
