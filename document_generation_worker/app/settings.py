from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local", alias="ENVIRONMENT")
    port: int = Field(default=8092, alias="PORT")
    log_level: str = Field(default="INFO", alias="DOCUMENT_GENERATION_LOG_LEVEL")

    backend_internal_base_url: str = Field(
        default="http://localhost:8001",
        alias="BACKEND_INTERNAL_BASE_URL",
    )
    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    gcp_region: str = Field(default="us-east1", alias="GCP_REGION")
    vertex_ai_location: str = Field(default="global", alias="VERTEX_AI_LOCATION")
    document_generation_provider: str = Field(
        default="anthropic_api",
        alias="DOCUMENT_GENERATION_PROVIDER",
    )
    document_generation_model: str | None = Field(
        default=None,
        alias="DOCUMENT_GENERATION_MODEL",
    )
    document_generation_google_model: str = Field(
        default="gemini-3.1-flash-lite-preview",
        validation_alias=AliasChoices(
            "DOCUMENT_GENERATION_GOOGLE_MODEL",
            "DOCUMENT_GENERATION_GEMINI_MODEL",
        ),
    )
    document_generation_anthropic_model: str = Field(
        default="claude-haiku-4-5-20251001",
        alias="DOCUMENT_GENERATION_ANTHROPIC_MODEL",
    )
    cloud_tasks_invoker_service_account: str | None = Field(
        default=None,
        alias="CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT",
    )
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_max_concurrent: int = Field(
        default=4,
        validation_alias=AliasChoices(
            "DOCUMENT_GENERATION_MAX_CONCURRENT",
            "LLM_MAX_CONCURRENT",
            "GEMINI_MAX_CONCURRENT",
        ),
    )
    chunk_size: int = Field(default=50, alias="DOCUMENT_GENERATION_CHUNK_SIZE")
    max_output_tokens: int = Field(
        default=8192,
        alias="DOCUMENT_GENERATION_MAX_OUTPUT_TOKENS",
    )
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_project: str | None = Field(default=None, alias="LANGSMITH_PROJECT")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_endpoint: str | None = Field(default=None, alias="LANGSMITH_ENDPOINT")

    @property
    def environment_name(self) -> str:
        return self.environment.strip().lower()

    @property
    def is_local(self) -> bool:
        return self.environment_name in {"local", "dev", "develop", "test"}

    @property
    def is_production(self) -> bool:
        return self.environment_name in {"prod", "production"}

    @property
    def langsmith_enabled(self) -> bool:
        return (
            not self.is_production
            and self.langsmith_tracing
            and bool((self.langsmith_project or "").strip())
            and bool((self.langsmith_api_key or "").strip())
        )

    @property
    def document_generation_provider_name(self) -> str:
        provider = self.document_generation_provider.strip().lower()
        aliases = {
            "gemini": "google_vertex",
            "google": "google_vertex",
            "google_genai": "google_vertex",
            "google_vertex": "google_vertex",
            "claude": "anthropic_api",
            "anthropic": "anthropic_api",
            "anthropic_api": "anthropic_api",
            "anthropic_vertex": "anthropic_vertex",
        }
        return aliases.get(provider, provider)

    @property
    def effective_document_generation_model(self) -> str:
        model = (self.document_generation_model or "").strip()
        if model:
            return model
        if self.document_generation_provider_name == "google_vertex":
            return self.document_generation_google_model
        return self.document_generation_anthropic_model
