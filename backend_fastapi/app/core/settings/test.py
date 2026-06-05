from __future__ import annotations

from pydantic import AliasChoices, Field

from app.core.settings.base import (
    BASE_DIR,
    COMMON_SETTINGS_CONFIG,
    CorsAllowedOrigins,
    LOCAL_CORS_ALLOWED_ORIGINS,
    Settings,
)


class TestSettings(Settings):
    model_config = COMMON_SETTINGS_CONFIG | {
        "env_file": (BASE_DIR / ".env.test",),
    }

    environment: str = Field(default="test", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    jwt_secret_key: str = Field(
        default="test-secret-at-least-32-bytes-long",
        alias="JWT_SECRET_KEY",
    )
    audit_ip_hmac_secret: str = Field(
        default="test-audit-ip-hmac-secret",
        alias="AUDIT_IP_HMAC_SECRET",
    )
    audit_ip_encryption_key: str = Field(
        default="Zb5QQ8mVdPPKZkhq0dQECjSlxMdkh2c8WqY2d9I4I1o=",
        alias="AUDIT_IP_ENCRYPTION_KEY",
    )
    cookie_secure: bool = Field(default=False, alias="FASTAPI_COOKIE_SECURE")
    cors_allowed_origins: CorsAllowedOrigins = Field(
        default_factory=lambda: LOCAL_CORS_ALLOWED_ORIGINS.copy(),
        validation_alias=AliasChoices(
            "FASTAPI_CORS_ALLOWED_ORIGINS",
            "CORS_ALLOWED_ORIGINS",
            "cors_allowed_origins",
        ),
    )
