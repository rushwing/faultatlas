import time
import logging
from openai import AsyncOpenAI
from redis.asyncio import Redis

from .prompts import SYSTEM_PROMPT, RAG_PROMPT
from .tools import retrieve_context
from ..config import Settings

logger = logging.getLogger(__name__)


async def run_agent(
    query: str,
    session_id: str,
    settings: Settings,
    redis: Redis,
) -> dict:
    """Single-step RAG agent: retrieve → synthesize → respond."""
    start = time.monotonic()

    chunks = await retrieve_context(
        query=query,
        retriever_url=settings.retriever_url,
        redis=redis,
    )

    context = "\n\n---\n\n".join(c["content"] for c in chunks)
    sources = [c.get("document_id", "") for c in chunks]

    prompt = RAG_PROMPT.format(context=context, question=query)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

    answer = response.choices[0].message.content or ""
    tokens_used = response.usage.total_tokens if response.usage else 0
    latency_ms = int((time.monotonic() - start) * 1000)

    logger.info(
        "agent completed",
        extra={"session_id": session_id, "tokens": tokens_used, "latency_ms": latency_ms},
    )
    return {"answer": answer, "sources": list(set(sources)), "tokens_used": tokens_used}
