from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    api_key: str = "changeme-local-dev"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "faultatlas"

    redis_url: str = "redis://localhost:6379/0"

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_consumer_group: str = "faultatlas-group"

    llm_backend: str = "openai"
    sglang_base_url: str = "http://localhost:8100/v1"
    model_name: str = "Qwen/Qwen2.5-7B-Instruct"
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"

    retriever_url: str = "http://localhost:8001"
    prompt_debug_enabled: bool = True
    max_query_tokens: int = 2000
    chunk_size: int = 512
    chunk_overlap: int = 64

    @field_validator("llm_backend")
    @classmethod
    def validate_llm_backend(cls, value: str) -> str:
        if value not in {"openai", "sglang"}:
            raise ValueError("LLM_BACKEND must be one of: openai, sglang")
        return value


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
