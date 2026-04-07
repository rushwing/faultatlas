import json
import re
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
        self._seen_prefixes: set[str] = set()

    @property
    def _root_url(self) -> str:
        return self._base_url[:-3] if self._base_url.endswith("/v1") else self._base_url

    def _is_fake_backend(self) -> bool:
        return self._model == "fake/sglang"

    def _extract_query(self, user_content: str) -> str:
        marker = "## Incident Description"
        if marker not in user_content:
            return "unknown incident"
        return user_content.split(marker, 1)[1].strip()

    def _extract_chunk_ids(self, user_content: str) -> list[str]:
        return re.findall(r"\[chunk_id=([^\s\]]+)", user_content)

    def _prefix_key(self, messages: list[dict[str, str]]) -> str:
        system = messages[0]["content"] if messages else ""
        user_content = messages[-1]["content"] if messages else ""
        marker = "## Incident Description"
        prefix = user_content.split(marker, 1)[0] if marker in user_content else user_content
        return system + "\n" + prefix

    async def _complete_fake(
        self,
        messages: list[dict[str, str]],
    ) -> LLMResponse:
        prefix_key = self._prefix_key(messages)
        shared_hit = prefix_key in self._seen_prefixes
        self._seen_prefixes.add(prefix_key)

        user_content = messages[-1]["content"] if messages else ""
        chunk_ids = self._extract_chunk_ids(user_content)
        query = self._extract_query(user_content)
        payload = {
            "summary": f"Diagnosis summary for {query}",
            "suspected_causes": ["memory pressure"] if chunk_ids else ["insufficient evidence"],
            "evidence_chunk_ids": chunk_ids[:1],
            "next_actions": ["Inspect the top cited chunk", "Check recent service restarts"],
            "confidence": "medium" if chunk_ids else "low",
        }
        content = json.dumps(payload)
        completion_tokens = max(len(content) // 4, 1)
        total_latency_ms = 10 if shared_hit else 50
        return LLMResponse(
            content=content,
            tokens_used=completion_tokens + 32,
            ttft_ms=max(total_latency_ms // completion_tokens, 1),
            total_latency_ms=total_latency_ms,
            prefix_cache_hint="shared" if shared_hit else "cold",
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> LLMResponse:
        if self._is_fake_backend():
            return await self._complete_fake(messages)

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
        if self._is_fake_backend():
            self._seen_prefixes.clear()
            return True

        for path in ("/flush_cache", "/v1/flush_cache"):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(f"{self._root_url}{path}")
            except httpx.HTTPError:
                continue
            if response.status_code < 400:
                return True
        return False
