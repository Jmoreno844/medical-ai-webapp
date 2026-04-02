from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field("local", alias="COPILOT_AGENT_ENV")
    port: int = Field(8090, alias="COPILOT_AGENT_PORT")
    log_level: str = Field("INFO", alias="COPILOT_AGENT_LOG_LEVEL")
    gcp_project_id: str = Field(..., alias="GCP_PROJECT_ID")
    gcp_region: str = Field(..., alias="GCP_REGION")
    vertex_model: str = Field("gemini-2.5-flash", alias="VERTEX_MODEL")
    planner_max_iterations: int = Field(
        6, alias="COPILOT_PLANNER_MAX_ITERATIONS"
    )
    database_url: str = Field(..., alias="COPILOT_AGENT_DATABASE_URL")
    long_term_database_url: str = Field(
        ..., alias="COPILOT_LONG_TERM_DATABASE_URL"
    )
    backend_internal_base_url: str = Field(
        ..., alias="BACKEND_INTERNAL_BASE_URL"
    )
    backend_internal_timeout_seconds: float = Field(
        15, alias="BACKEND_INTERNAL_TIMEOUT_SECONDS"
    )
    backend_audience: str = Field(
        "medical-api", alias="COPILOT_BACKEND_AUDIENCE"
    )
    service_shared_jwt: str = Field(..., alias="COPILOT_SERVICE_SHARED_JWT")
    allowed_audience: str = Field(
        "app-api-service", alias="COPILOT_ALLOWED_AUDIENCE"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
