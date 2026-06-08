from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local", alias="ENVIRONMENT")
    port: int = Field(default=8093, alias="PORT")
    log_level: str = Field(default="INFO", alias="CLINICAL_EXTRACTION_LOG_LEVEL")
    backend_internal_base_url: str = Field(
        default="http://localhost:8001",
        alias="BACKEND_INTERNAL_BASE_URL",
    )
    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    vertex_ai_location: str = Field(default="global", alias="VERTEX_AI_LOCATION")
    clinical_extraction_provider: str = Field(
        default="gemini",
        alias="CLINICAL_EXTRACTION_PROVIDER",
    )
    clinical_extraction_model: str = Field(
        default="gemini-2.5-flash",
        alias="CLINICAL_EXTRACTION_MODEL",
    )
    clinical_extraction_openai_model: str = Field(
        default="gpt-5.4-mini",
        alias="CLINICAL_EXTRACTION_OPENAI_MODEL",
    )
    clinical_extraction_max_concurrent: int = Field(
        default=4,
        alias="CLINICAL_EXTRACTION_MAX_CONCURRENT",
    )
    clinical_extraction_max_output_tokens: int = Field(
        default=16384,
        alias="CLINICAL_EXTRACTION_MAX_OUTPUT_TOKENS",
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    cloud_tasks_invoker_service_account: str | None = Field(
        default=None,
        alias="CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT",
    )

    @property
    def environment_name(self) -> str:
        return self.environment.strip().lower()

    @property
    def is_local(self) -> bool:
        return self.environment_name in {"local", "dev", "develop", "test"}

    @property
    def provider_name(self) -> str:
        provider = self.clinical_extraction_provider.strip().lower()
        aliases = {
            "google": "gemini",
            "google_vertex": "gemini",
            "google_genai": "gemini",
            "gemini": "gemini",
            "openai": "openai",
        }
        return aliases.get(provider, provider)

    @property
    def effective_model(self) -> str:
        if self.provider_name == "openai":
            return self.clinical_extraction_openai_model
        return self.clinical_extraction_model
