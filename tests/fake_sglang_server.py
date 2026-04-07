from __future__ import annotations

import asyncio
import json
import re

import uvicorn
from fastapi import FastAPI, Response
from pydantic import BaseModel

app = FastAPI(title="Fake SGLang")
_seen_prefixes: set[str] = set()


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]


def _extract_chunk_ids(user_content: str) -> list[str]:
    return re.findall(r"\[chunk_id=([^\s\]]+)", user_content)


def _extract_query(user_content: str) -> str:
    marker = "## Incident Description"
    if marker not in user_content:
        return "unknown incident"
    return user_content.split(marker, 1)[1].strip()


def _prefix_key(messages: list[dict[str, str]]) -> str:
    system = messages[0]["content"]
    user_content = messages[-1]["content"]
    marker = "## Incident Description"
    prefix = user_content.split(marker, 1)[0] if marker in user_content else user_content
    return system + "\n" + prefix


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/flush_cache")
async def flush_cache() -> dict:
    _seen_prefixes.clear()
    return {"flushed": True}


@app.post("/v1/flush_cache")
async def flush_cache_v1() -> dict:
    return await flush_cache()


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, response: Response) -> dict:
    prefix_key = _prefix_key(request.messages)
    shared_hit = prefix_key in _seen_prefixes
    _seen_prefixes.add(prefix_key)
    response.headers["x-prefix-cache-hit"] = "true" if shared_hit else "false"
    await asyncio.sleep(0.01 if shared_hit else 0.05)

    user_content = request.messages[-1]["content"]
    chunk_ids = _extract_chunk_ids(user_content)
    query = _extract_query(user_content)
    payload = {
        "summary": f"Diagnosis summary for {query}",
        "suspected_causes": ["memory pressure"] if chunk_ids else ["insufficient evidence"],
        "evidence_chunk_ids": chunk_ids[:1],
        "next_actions": ["Inspect the top cited chunk", "Check recent service restarts"],
        "confidence": "medium" if chunk_ids else "low",
    }
    content = json.dumps(payload)
    completion_tokens = max(len(content) // 4, 1)
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": max(sum(len(m["content"]) for m in request.messages) // 4, 1),
            "completion_tokens": completion_tokens,
            "total_tokens": completion_tokens + 32,
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)
