from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "investment-research-platform"
    app_version: str = "0.1.0"
    app_env: str = "local"
    database_url: str = "postgresql://localhost:5432/investment_research_mvp"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_pool_timeout: float = 30.0
    upload_dir: Path = Path("data/uploads")
    export_dir: Path = Path("data/exports")
    llm_provider: str = "external"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    embedding_provider: str = "local_hash"
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    rerank_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
