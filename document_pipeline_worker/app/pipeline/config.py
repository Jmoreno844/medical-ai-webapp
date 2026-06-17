from __future__ import annotations

from dataclasses import dataclass

from document_pipeline_core.common.pipeline_steps import CONTEXT_PIPELINE_SUBSTEPS
from document_pipeline_core.orchestrators.config import PRODUCTION_PIPELINE_DEFAULTS
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
    """Production pipeline config aligned with shared document_pipeline_core registry."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        extra="ignore",
        populate_by_name=True,
    )

    filtering_provider: str = Field(default="google_vertex", alias="PIPELINE_FILTERING_PROVIDER")
    filtering_model: str = Field(default="", alias="PIPELINE_FILTERING_MODEL")
    filtering_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.filtering,
        alias="PIPELINE_FILTERING_PROMPT_VERSION",
    )
    filtering_strategy: str = Field(default="default", alias="PIPELINE_FILTERING_STRATEGY")

    clustering_provider: str = Field(default="google_vertex", alias="PIPELINE_CLUSTERING_PROVIDER")
    clustering_model: str = Field(default="", alias="PIPELINE_CLUSTERING_MODEL")
    clustering_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.clustering,
        alias="PIPELINE_CLUSTERING_PROMPT_VERSION",
    )
    clustering_strategy: str = Field(default="with_repair", alias="PIPELINE_CLUSTERING_STRATEGY")

    classification_provider: str = Field(
        default="google_vertex",
        alias="PIPELINE_CLASSIFICATION_PROVIDER",
    )
    classification_model: str = Field(default="", alias="PIPELINE_CLASSIFICATION_MODEL")
    classification_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.classification,
        alias="PIPELINE_CLASSIFICATION_PROMPT_VERSION",
    )
    classification_strategy: str = Field(default="session", alias="PIPELINE_CLASSIFICATION_STRATEGY")

    context_provider: str = Field(default="google_vertex", alias="PIPELINE_CONTEXT_PROVIDER")
    context_model: str = Field(default="", alias="PIPELINE_CONTEXT_MODEL")
    context_strategy: str = Field(default="v2", alias="PIPELINE_CONTEXT_STRATEGY")
    context_enabled: bool = Field(default=True, alias="PIPELINE_CONTEXT_ENABLED")

    context_triage_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.resolved_context_substeps()["context_triage"],
        alias="PIPELINE_CONTEXT_TRIAGE_PROMPT_VERSION",
    )
    context_filter_spans_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.resolved_context_substeps()["context_filter_spans"],
        alias="PIPELINE_CONTEXT_FILTER_SPANS_PROMPT_VERSION",
    )
    context_document_directive_filter_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.resolved_context_substeps()[
            "context_document_directive_filter"
        ],
        alias="PIPELINE_CONTEXT_DOCUMENT_DIRECTIVE_FILTER_PROMPT_VERSION",
    )
    context_cluster_spans_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.resolved_context_substeps()["context_cluster_spans"],
        alias="PIPELINE_CONTEXT_CLUSTER_SPANS_PROMPT_VERSION",
    )
    context_classify_clusters_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.resolved_context_substeps()[
            "context_classify_clusters"
        ],
        alias="PIPELINE_CONTEXT_CLASSIFY_CLUSTERS_PROMPT_VERSION",
    )
    context_section_adapter_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.resolved_context_substeps()["context_section_adapter"],
        alias="PIPELINE_CONTEXT_SECTION_ADAPTER_PROMPT_VERSION",
    )

    generation_provider: str = Field(default="google_vertex", alias="PIPELINE_GENERATION_PROVIDER")
    generation_model: str = Field(default="", alias="PIPELINE_GENERATION_MODEL")
    generation_prompt_version: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.generation_direct,
        alias="PIPELINE_GENERATION_PROMPT_VERSION",
    )
    generation_route: str = Field(
        default=PRODUCTION_PIPELINE_DEFAULTS.generation_route,
        alias="PIPELINE_GENERATION_ROUTE",
    )
    generation_strategy: str = Field(
        default="single_call_per_section",
        alias="PIPELINE_GENERATION_STRATEGY",
    )
    generation_section_concurrency: int = Field(
        default=4,
        alias="PIPELINE_GENERATION_SECTION_CONCURRENCY",
    )

    def context_prompt_versions(self) -> dict[str, str]:
        return {
            "context_triage": self.context_triage_prompt_version,
            "context_filter_spans": self.context_filter_spans_prompt_version,
            "context_document_directive_filter": self.context_document_directive_filter_prompt_version,
            "context_cluster_spans": self.context_cluster_spans_prompt_version,
            "context_classify_clusters": self.context_classify_clusters_prompt_version,
            "context_section_adapter": self.context_section_adapter_prompt_version,
        }

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
                self.context_triage_prompt_version,
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

    def validate_context_substeps(self) -> None:
        versions = self.context_prompt_versions()
        missing = [step for step in CONTEXT_PIPELINE_SUBSTEPS if step not in versions]
        if missing:
            raise ValueError(f"pipeline_context_substeps_incomplete: {missing}")
