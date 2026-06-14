from __future__ import annotations

from pydantic import AliasChoices, Field
from worker_runtime.settings import BaseWorkerSettings

from app.pipeline.config import PipelineConfig


class Settings(BaseWorkerSettings, PipelineConfig):
    port: int = Field(default=8092, alias="PORT")
    log_level: str = Field(default="INFO", alias="DOCUMENT_PIPELINE_LOG_LEVEL")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_max_concurrent: int = Field(
        default=4,
        validation_alias=AliasChoices(
            "DOCUMENT_PIPELINE_MAX_CONCURRENT",
            "LLM_MAX_CONCURRENT",
        ),
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
    def pipeline_config(self) -> PipelineConfig:
        return PipelineConfig.model_validate(self.model_dump())
