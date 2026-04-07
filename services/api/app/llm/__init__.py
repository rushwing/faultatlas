from .backends.openai import OpenAILLMClient
from .backends.sglang import SGLangLLMClient
from .client import LLMClient, LLMResponse


def get_llm_client(settings) -> LLMClient:
    if settings.llm_backend == "openai":
        return OpenAILLMClient(settings)
    return SGLangLLMClient(settings)


__all__ = ["LLMClient", "LLMResponse", "get_llm_client"]
