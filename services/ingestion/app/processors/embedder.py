import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


async def embed_chunks(chunks: list[str], model: str, api_key: str) -> list[list[float]]:
    client = AsyncOpenAI(api_key=api_key)
    # Batch in groups of 100 (OpenAI limit)
    all_embeddings: list[list[float]] = []
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        response = await client.embeddings.create(input=batch, model=model)
        all_embeddings.extend([r.embedding for r in response.data])
        logger.debug("embedded batch", extra={"batch": i // batch_size, "count": len(batch)})
    return all_embeddings
