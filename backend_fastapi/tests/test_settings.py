import pytest

from app.core.config import Settings, get_settings
from app.core.settings import (
    LocalSettings,
    ProductionSettings,
    StagingSettings,
    TestSettings as FastAPITestSettings,
)


def test_settings_selects_class_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [
        ("local", LocalSettings),
        ("dev", LocalSettings),
        ("test", FastAPITestSettings),
        ("ci", FastAPITestSettings),
        ("stg", StagingSettings),
        ("production", ProductionSettings),
    ]

    for environment, expected_class in cases:
        monkeypatch.setenv("ENVIRONMENT", environment)
        if expected_class in {ProductionSettings, StagingSettings}:
            monkeypatch.setenv("JWT_SECRET_KEY", "prod-secret-at-least-32-bytes-long")
            monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db:5432/app")
            monkeypatch.setenv("FASTAPI_CORS_ALLOWED_ORIGINS", "https://app.example")
            monkeypatch.setenv("GCP_PROJECT_ID", "medical-prod")
            monkeypatch.setenv("GCS_BUCKET_NAME", "medical-audio-prod")
            monkeypatch.setenv("COPILOT_SERVICE_SHARED_JWT", "copilot-shared-secret")
        get_settings.cache_clear()

        assert isinstance(get_settings(), expected_class)

    get_settings.cache_clear()


def test_local_and_test_settings_have_safe_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("FASTAPI_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    local_settings = LocalSettings(_env_file=None)
    test_settings = FastAPITestSettings(_env_file=None)

    assert local_settings.debug is True
    assert local_settings.cookie_secure is False
    assert "http://localhost:5173" in local_settings.cors_allowed_origins
    assert test_settings.debug is False
    assert test_settings.cookie_secure is False
    assert test_settings.token_signing_key == "test-secret-at-least-32-bytes-long"


def test_production_requires_deployment_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in [
        "JWT_SECRET_KEY",
        "DATABASE_URL",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_HOST",
        "FASTAPI_CORS_ALLOWED_ORIGINS",
        "GCP_PROJECT_ID",
        "GCS_BUCKET_NAME",
        "COPILOT_SERVICE_SHARED_JWT",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="Missing required FastAPI deployment settings"):
        ProductionSettings()


def test_production_accepts_explicit_deployment_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "prod-secret-at-least-32-bytes-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db:5432/app")
    monkeypatch.setenv("FASTAPI_CORS_ALLOWED_ORIGINS", "https://app.example")
    monkeypatch.setenv("GCP_PROJECT_ID", "medical-prod")
    monkeypatch.setenv("GCS_BUCKET_NAME", "medical-audio-prod")
    monkeypatch.setenv("COPILOT_SERVICE_SHARED_JWT", "copilot-shared-secret")

    settings = ProductionSettings()

    assert settings.cookie_secure is True
    assert settings.cors_allowed_origins == ["https://app.example"]


def test_database_url_takes_precedence_over_parts() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://url_user:url_pass@url-host:5432/url_db",
        DB_NAME="parts_db",
        DB_USER="parts_user",
        DB_PASSWORD="parts_pass",
        DB_HOST="parts-host",
    )

    assert settings.async_database_url == (
        "postgresql+asyncpg://url_user:url_pass@url-host:5432/url_db"
    )
