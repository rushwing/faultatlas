from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    api_key: str = "changeme-local-dev"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "faultatlas"

    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"

    default_top_k: int = 5


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
