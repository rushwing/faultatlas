import pytest

from services.api.app.config import Settings
from services.api.app.llm.backends.sglang import SGLangLLMClient


def _messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "fixed system prompt"},
        {
            "role": "user",
            "content": (
                "## Retrieved Evidence\n"
                "[chunk_id=chunk-1 document_id=doc-1 score=0.900]\nOOM log\n\n"
                "## Incident Description\nWhy is the service crashing?"
            ),
        },
    ]


@pytest.mark.asyncio
async def test_fake_backend_prefix_cache_state_is_instance_local() -> None:
    settings = Settings(
        openai_api_key="test-key",
        llm_backend="sglang",
        model_name="fake/sglang",
        sglang_base_url="http://127.0.0.1:8100/v1",
    )

    first_client = SGLangLLMClient(settings)
    second_client = SGLangLLMClient(settings)

    first_response = await first_client.complete(_messages())
    second_response = await second_client.complete(_messages())

    assert first_response.prefix_cache_hint == "cold"
    assert second_response.prefix_cache_hint == "cold"


@pytest.mark.asyncio
async def test_fake_backend_reuses_prefixes_within_single_instance() -> None:
    settings = Settings(
        openai_api_key="test-key",
        llm_backend="sglang",
        model_name="fake/sglang",
        sglang_base_url="http://127.0.0.1:8100/v1",
    )

    client = SGLangLLMClient(settings)

    first_response = await client.complete(_messages())
    second_response = await client.complete(_messages())

    assert first_response.prefix_cache_hint == "cold"
    assert second_response.prefix_cache_hint == "shared"
