from __future__ import annotations

from pydantic import Field
from worker_runtime.settings import BaseWorkerSettings


class Settings(BaseWorkerSettings):
    port: int = Field(default=8093, alias="PORT")
    log_level: str = Field(default="INFO", alias="CLINICAL_EXTRACTION_LOG_LEVEL")
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
    clinical_extraction_anthropic_model: str = Field(
        default="claude-haiku-4-5-20251001",
        alias="CLINICAL_EXTRACTION_ANTHROPIC_MODEL",
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
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    @property
    def provider_name(self) -> str:
        provider = self.clinical_extraction_provider.strip().lower()
        aliases = {
            "google": "gemini",
            "google_vertex": "gemini",
            "google_genai": "gemini",
            "gemini": "gemini",
            "openai": "openai",
            "claude": "anthropic_api",
            "anthropic": "anthropic_api",
            "anthropic_api": "anthropic_api",
        }
        return aliases.get(provider, provider)

    @property
    def effective_model(self) -> str:
        if self.provider_name == "openai":
            return self.clinical_extraction_openai_model
        if self.provider_name == "anthropic_api":
            return self.clinical_extraction_anthropic_model
        return self.clinical_extraction_model
