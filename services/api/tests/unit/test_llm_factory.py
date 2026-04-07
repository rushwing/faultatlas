from services.api.app.config import Settings
from services.api.app.llm import get_llm_client
from services.api.app.llm.backends.openai import OpenAILLMClient
from services.api.app.llm.backends.sglang import SGLangLLMClient


def test_get_llm_client_returns_openai_client() -> None:
    settings = Settings(openai_api_key="test-key", llm_backend="openai")
    assert isinstance(get_llm_client(settings), OpenAILLMClient)


def test_get_llm_client_returns_sglang_client() -> None:
    settings = Settings(openai_api_key="test-key", llm_backend="sglang")
    assert isinstance(get_llm_client(settings), SGLangLLMClient)
