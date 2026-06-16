from __future__ import annotations

from dataclasses import dataclass

from document_pipeline_core.common.pipeline_steps import (
    CONTEXT_PIPELINE_SUBSTEPS,
    default_context_substep_versions,
    default_prompt_version,
)


@dataclass(frozen=True, slots=True)
class StepModelConfig:
    provider: str
    model: str
    prompt_version: str
    strategy: str = "default"


@dataclass(frozen=True, slots=True)
class ProductionPipelineDefaults:
    """Stable production prompt versions aligned with the R&D harness."""

    filtering: str = "v002"
    clustering: str = "v002"
    classification: str = "v004"
    generation_route: str = "direct"
    generation_direct: str = "v001"
    generation_planner: str = "v001"
    generation_renderer: str = "v001"
    context_substeps: dict[str, str] | None = None

    def resolved_context_substeps(self) -> dict[str, str]:
        if self.context_substeps is not None:
            return dict(self.context_substeps)
        return default_context_substep_versions()


PRODUCTION_PIPELINE_DEFAULTS = ProductionPipelineDefaults()


def production_step_prompt_version(step: str) -> str:
    defaults = PRODUCTION_PIPELINE_DEFAULTS
    if step == "filtering":
        return defaults.filtering
    if step == "clustering":
        return defaults.clustering
    if step == "classification":
        return defaults.classification
    if step == "generation":
        return defaults.generation_direct
    if step in CONTEXT_PIPELINE_SUBSTEPS:
        return defaults.resolved_context_substeps()[step]
    return default_prompt_version(step)


__all__ = [
    "PRODUCTION_PIPELINE_DEFAULTS",
    "ProductionPipelineDefaults",
    "StepModelConfig",
    "production_step_prompt_version",
]
