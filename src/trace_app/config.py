"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings, loaded from environment variables."""

    database_url: str
    log_level: str = "INFO"
    embedding_model: str = "bge-small-en-v1.5"
    embedding_dimension: int = 384

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
