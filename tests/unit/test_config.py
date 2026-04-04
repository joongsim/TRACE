import pytest

from trace_app.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should load DATABASE_URL from environment."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/trace")
    settings = Settings()  # ty: ignore[missing-argument]
    assert str(settings.database_url) == "postgresql+psycopg://user:pass@localhost:5432/trace"


def test_settings_default_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should have sensible defaults for optional fields."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/trace")
    settings = Settings()  # ty: ignore[missing-argument]
    assert settings.log_level == "INFO"
    assert settings.embedding_model == "bge-small-en-v1.5"
    assert settings.embedding_dimension == 384
