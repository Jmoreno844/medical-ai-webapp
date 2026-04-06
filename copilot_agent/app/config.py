from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ProviderFamily = Literal["google", "openai", "anthropic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field("local", alias="COPILOT_AGENT_ENV")
    port: int = Field(8090, alias="COPILOT_AGENT_PORT")
    log_level: str = Field("INFO", alias="COPILOT_AGENT_LOG_LEVEL")
    gcp_project_id: str | None = Field(None, alias="GCP_PROJECT_ID")
    gcp_region: str | None = Field(None, alias="GCP_REGION")
    vertex_model: str = Field("gemini-2.5-flash", alias="VERTEX_MODEL")
    llm_provider_family: ProviderFamily = Field(
        "openai", alias="COPILOT_LLM_PROVIDER_FAMILY"
    )
    planner_provider_family: ProviderFamily | None = Field(
        None, alias="COPILOT_PLANNER_PROVIDER_FAMILY"
    )
    planner_model: str | None = Field(None, alias="COPILOT_PLANNER_MODEL")
    patch_provider_family: ProviderFamily | None = Field(
        None, alias="COPILOT_PATCH_PROVIDER_FAMILY"
    )
    patch_model: str | None = Field(None, alias="COPILOT_PATCH_MODEL")
    google_location: str | None = Field(None, alias="COPILOT_GOOGLE_LOCATION")
    planner_google_location: str | None = Field(
        None, alias="COPILOT_PLANNER_GOOGLE_LOCATION"
    )
    patch_google_location: str | None = Field(
        None, alias="COPILOT_PATCH_GOOGLE_LOCATION"
    )
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    langsmith_tracing: bool | None = Field(None, alias="LANGSMITH_TRACING")
    langsmith_api_key: str | None = Field(None, alias="LANGSMITH_API_KEY")
    langsmith_project: str | None = Field(None, alias="LANGSMITH_PROJECT")
    langsmith_endpoint: str | None = Field(None, alias="LANGSMITH_ENDPOINT")
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
