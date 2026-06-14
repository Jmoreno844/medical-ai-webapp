from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True, slots=True)
class StepConfig:
    provider: str
    model: str
    prompt_version: str
    strategy: str = "default"


PIPELINE_STEPS = (
    "filtering",
    "clustering",
    "classification",
    "context",
    "generation",
)


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    filtering_provider: str = Field(default="google_vertex", alias="PIPELINE_FILTERING_PROVIDER")
    filtering_model: str = Field(default="", alias="PIPELINE_FILTERING_MODEL")
    filtering_prompt_version: str = Field(default="v001", alias="PIPELINE_FILTERING_PROMPT_VERSION")
    filtering_strategy: str = Field(default="default", alias="PIPELINE_FILTERING_STRATEGY")

    clustering_provider: str = Field(default="google_vertex", alias="PIPELINE_CLUSTERING_PROVIDER")
    clustering_model: str = Field(default="", alias="PIPELINE_CLUSTERING_MODEL")
    clustering_prompt_version: str = Field(default="v001", alias="PIPELINE_CLUSTERING_PROMPT_VERSION")
    clustering_strategy: str = Field(default="with_repair", alias="PIPELINE_CLUSTERING_STRATEGY")

    classification_provider: str = Field(
        default="google_vertex",
        alias="PIPELINE_CLASSIFICATION_PROVIDER",
    )
    classification_model: str = Field(default="", alias="PIPELINE_CLASSIFICATION_MODEL")
    classification_prompt_version: str = Field(
        default="v003",
        alias="PIPELINE_CLASSIFICATION_PROMPT_VERSION",
    )
    classification_strategy: str = Field(default="session", alias="PIPELINE_CLASSIFICATION_STRATEGY")

    context_provider: str = Field(default="google_vertex", alias="PIPELINE_CONTEXT_PROVIDER")
    context_model: str = Field(default="", alias="PIPELINE_CONTEXT_MODEL")
    context_decompose_prompt_version: str = Field(
        default="v001",
        alias="PIPELINE_CONTEXT_DECOMPOSE_PROMPT_VERSION",
    )
    context_classify_prompt_version: str = Field(
        default="v001",
        alias="PIPELINE_CONTEXT_CLASSIFY_PROMPT_VERSION",
    )
    context_strategy: str = Field(default="doctor_note_only", alias="PIPELINE_CONTEXT_STRATEGY")
    context_enabled: bool = Field(default=True, alias="PIPELINE_CONTEXT_ENABLED")

    generation_provider: str = Field(default="google_vertex", alias="PIPELINE_GENERATION_PROVIDER")
    generation_model: str = Field(default="", alias="PIPELINE_GENERATION_MODEL")
    generation_prompt_version: str = Field(default="v002", alias="PIPELINE_GENERATION_PROMPT_VERSION")
    generation_strategy: str = Field(
        default="single_call_per_section",
        alias="PIPELINE_GENERATION_STRATEGY",
    )
    generation_section_concurrency: int = Field(
        default=4,
        alias="PIPELINE_GENERATION_SECTION_CONCURRENCY",
    )

    def step_config(self, step: str) -> StepConfig:
        if step == "filtering":
            return StepConfig(
                self.filtering_provider,
                self.filtering_model,
                self.filtering_prompt_version,
                self.filtering_strategy,
            )
        if step == "clustering":
            return StepConfig(
                self.clustering_provider,
                self.clustering_model,
                self.clustering_prompt_version,
                self.clustering_strategy,
            )
        if step == "classification":
            return StepConfig(
                self.classification_provider,
                self.classification_model,
                self.classification_prompt_version,
                self.classification_strategy,
            )
        if step == "context":
            return StepConfig(
                self.context_provider,
                self.context_model,
                self.context_decompose_prompt_version,
                self.context_strategy,
            )
        if step == "generation":
            return StepConfig(
                self.generation_provider,
                self.generation_model,
                self.generation_prompt_version,
                self.generation_strategy,
            )
        raise ValueError(f"unknown_pipeline_step: {step}")
