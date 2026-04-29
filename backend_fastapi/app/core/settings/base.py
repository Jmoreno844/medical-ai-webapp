from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]
REPO_DIR = BASE_DIR.parent

COMMON_SETTINGS_CONFIG = SettingsConfigDict(
    env_file_encoding="utf-8",
    extra="ignore",
    populate_by_name=True,
)

LOCAL_CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CorsAllowedOrigins = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = COMMON_SETTINGS_CONFIG

    environment: str = Field(default="local", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    api_v1_prefix: str = "/api/v1"

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_name: str | None = Field(default=None, alias="DB_NAME")
    db_user: str | None = Field(default=None, alias="DB_USER")
    db_password: str | None = Field(default=None, alias="DB_PASSWORD")
    db_host: str | None = Field(default=None, alias="DB_HOST")
    db_port: str = Field(default="5432", alias="DB_PORT")

    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    gcs_bucket_name: str | None = Field(default=None, alias="GCS_BUCKET_NAME")
    gcp_stt_location: str = Field(default="us", alias="GCP_STT_LOCATION")
    gcp_stt_model: str = Field(default="chirp_3", alias="GCP_STT_MODEL")
    gcp_storage_impersonated_service_account: str | None = Field(
        default=None,
        alias="GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT",
    )
    gcp_storage_service_account_key_path: str | None = Field(
        default=None,
        alias="GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH",
    )
    service_account_json: str | None = Field(default=None, alias="SERVICE_ACCOUNT_JSON")

    jwt_secret_key: str = Field(default="not-loaded", alias="JWT_SECRET_KEY")
    jwt_issuer: str = "medical-web-app-fastapi"
    browser_jwt_audience: str = "medical-api-browser"
    sse_jwt_audience: str = "medical-api-sse"
    callback_jwt_audience: str = "medical-api-callbacks"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    sse_token_minutes: int = 5
    transcription_callback_token_minutes: int = 15
    generation_callback_token_minutes: int = 30

    transcription_task_target_url: str | None = Field(
        default=None,
        alias="TRANSCRIPTION_TASK_TARGET_URL",
    )
    vertex_ai_location: str | None = Field(default="global", alias="VERTEX_AI_LOCATION")
    document_generation_task_target_url: str | None = Field(
        default=None,
        alias="DOCUMENT_GENERATION_TASK_TARGET_URL",
    )
    document_generation_queue_name: str | None = Field(
        default=None,
        alias="DOCUMENT_GENERATION_QUEUE_NAME",
    )
    document_generation_worker_service_account: str | None = Field(
        default=None,
        alias="DOCUMENT_GENERATION_WORKER_SERVICE_ACCOUNT",
    )
    document_generation_worker_base_url: str | None = Field(
        default=None,
        alias="DOCUMENT_GENERATION_WORKER_BASE_URL",
    )
    document_generation_gemini_model: str = Field(
        default="gemini-3.1-flash-lite-preview",
        alias="DOCUMENT_GENERATION_GEMINI_MODEL",
    )
    copilot_agent_base_url: str = Field(
        default="http://localhost:8010",
        alias="COPILOT_AGENT_BASE_URL",
    )
    copilot_service_shared_jwt: str = Field(
        default="not-loaded",
        alias="COPILOT_SERVICE_SHARED_JWT",
    )
    copilot_agent_audience: str = Field(
        default="app-api-service",
        alias="COPILOT_AGENT_AUDIENCE",
    )
    copilot_backend_audience: str = Field(
        default="medical-api",
        alias="COPILOT_BACKEND_AUDIENCE",
    )
    copilot_agent_timeout_seconds: float = Field(
        default=60.0,
        alias="COPILOT_AGENT_TIMEOUT_SECONDS",
    )
    cloud_tasks_region: str | None = Field(default=None, alias="CLOUD_TASKS_REGION")
    transcription_queue_name: str | None = Field(
        default=None,
        alias="TRANSCRIPTION_QUEUE_NAME",
    )
    cloud_tasks_invoker_service_account: str | None = Field(
        default=None,
        alias="CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT",
    )
    transcription_worker_service_account: str | None = Field(
        default=None,
        alias="TRANSCRIPTION_WORKER_SERVICE_ACCOUNT",
    )
    transcription_worker_base_url: str | None = Field(
        default=None,
        alias="TRANSCRIPTION_WORKER_BASE_URL",
    )

    access_cookie_name: str = "medical_access_token"
    refresh_cookie_name: str = "medical_refresh_token"
    csrf_cookie_name: str = "_xsrf"
    csrf_header_name: str = "x-csrftoken"
    cookie_secure: bool = Field(default=False, alias="FASTAPI_COOKIE_SECURE")
    cookie_samesite: str = Field(default="lax", alias="FASTAPI_COOKIE_SAMESITE")

    cors_allowed_origins: CorsAllowedOrigins = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "FASTAPI_CORS_ALLOWED_ORIGINS",
            "CORS_ALLOWED_ORIGINS",
            "cors_allowed_origins",
        ),
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return value
        return []

    @field_validator("debug", "cookie_secure", mode="before")
    @classmethod
    def parse_bool(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "debug"}
        return False

    @property
    def async_database_url(self) -> str:
        if self.database_url:
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        if not (self.db_name and self.db_user and self.db_host):
            return "postgresql+asyncpg://not-configured:not-configured@localhost:5432/not-configured"

        user = quote_plus(self.db_user)
        password = f":{quote_plus(self.db_password)}" if self.db_password else ""
        return (
            f"postgresql+asyncpg://{user}{password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def token_signing_key(self) -> str:
        if self.jwt_secret_key and self.jwt_secret_key != "not-loaded":
            return self.jwt_secret_key
        raise RuntimeError("JWT_SECRET_KEY must be configured for FastAPI auth")


class StrictDeploymentSettings(Settings):
    debug: bool = Field(default=False, alias="DEBUG")
    cookie_secure: bool = Field(default=True, alias="FASTAPI_COOKIE_SECURE")

    @model_validator(mode="after")
    def validate_deployment_settings(self) -> StrictDeploymentSettings:
        missing: list[str] = []
        if not self.jwt_secret_key or self.jwt_secret_key == "not-loaded":
            missing.append("JWT_SECRET_KEY")
        if not self.database_url and not (
            self.db_name and self.db_user and self.db_host
        ):
            missing.append("DATABASE_URL or DB_NAME/DB_USER/DB_HOST")
        if not self.cors_allowed_origins:
            missing.append("FASTAPI_CORS_ALLOWED_ORIGINS")
        if not self.gcp_project_id:
            missing.append("GCP_PROJECT_ID")
        if not self.gcs_bucket_name:
            missing.append("GCS_BUCKET_NAME")
        if (
            not self.copilot_service_shared_jwt
            or self.copilot_service_shared_jwt == "not-loaded"
        ):
            missing.append("COPILOT_SERVICE_SHARED_JWT")
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required FastAPI deployment settings: {joined}")
        return self
