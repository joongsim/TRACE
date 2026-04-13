"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings, loaded from environment variables."""

    database_url: str
    log_level: str = "INFO"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    docling_url: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
