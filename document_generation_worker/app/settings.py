from __future__ import annotations

from pydantic import AliasChoices, Field
from worker_runtime.settings import BaseWorkerSettings


class Settings(BaseWorkerSettings):
    port: int = Field(default=8092, alias="PORT")
    log_level: str = Field(default="INFO", alias="DOCUMENT_GENERATION_LOG_LEVEL")
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
