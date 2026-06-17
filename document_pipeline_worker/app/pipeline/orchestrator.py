from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from document_pipeline_core.common.context_inputs import ContextInputs
from document_pipeline_core.common.templates import ClinicalTemplate
from document_pipeline_core.context_pipeline.config import ContextPipelineConfig
from document_pipeline_core.orchestrators.config import StepModelConfig
from document_pipeline_core.orchestrators.document_pipeline import (
    DocumentPipelineRunResult,
    DocumentPipelineStepResult,
    build_model_spec,
    run_document_pipeline_v2,
)

from app.pipeline.config import PipelineConfig
from app.pipeline.generation_route import (
    ResolvedGenerationRoute,
    resolve_effective_generation_route,
)


PIPELINE_STEP_LABELS: dict[str, str] = {
    "filtering": "Filtrando turnos de la transcripción",
    "clustering": "Agrupando temas clínicos",
    "classification": "Clasificando clusters en secciones",
    "context": "Procesando contexto clínico",
    "generation": "Generando documento por secciones",
}


@dataclass(frozen=True, slots=True)
class PipelineStepResult:
    step: str
    duration_ms: int
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    document_markdown: str
    step_results: list[PipelineStepResult]


def parse_context_inputs(work_item: dict[str, Any]) -> ContextInputs:
    raw = work_item.get("context_inputs")
    if isinstance(raw, dict):
        return ContextInputs.model_validate(raw)
    legacy = str(work_item.get("context_content") or "").strip()
    return ContextInputs(
        doctor_note_markdown=legacy or None,
        external_documents=[],
    )


def _to_step_model(config: PipelineConfig, step: str) -> StepModelConfig:
    step_cfg = config.step_config(step)
    return StepModelConfig(
        provider=step_cfg.provider,
        model=step_cfg.model,
        prompt_version=step_cfg.prompt_version,
        strategy=step_cfg.strategy,
    )


def run_document_pipeline(
    *,
    session_id: str,
    template: ClinicalTemplate,
    transcript_json: dict[str, object],
    context_inputs: ContextInputs,
    pipeline_config: PipelineConfig,
    on_step_complete: Callable[[str, dict[str, object]], None] | None = None,
    on_section_complete: Callable[[str, str, str], None] | None = None,
) -> PipelineRunResult:
    pipeline_config.validate_context_substeps()
    resolved_route = resolve_effective_generation_route(
        template=template,
        pipeline_config=pipeline_config,
    )
    context_config = ContextPipelineConfig.with_defaults(
        pipeline_config.context_prompt_versions()
    )
    core_result: DocumentPipelineRunResult = run_document_pipeline_v2(
        session_id=session_id,
        template=template,
        transcript_json=transcript_json,
        context_inputs=context_inputs,
        filtering_config=_to_step_model(pipeline_config, "filtering"),
        clustering_config=_to_step_model(pipeline_config, "clustering"),
        classification_config=_to_step_model(pipeline_config, "classification"),
        context_config=context_config,
        context_model=_to_step_model(pipeline_config, "context"),
        generation_config=_to_step_model(pipeline_config, "generation"),
        generation_route=resolved_route.effective_generation_route,
        context_enabled=pipeline_config.context_enabled,
        section_concurrency=pipeline_config.generation_section_concurrency,
        on_step_complete=on_step_complete,
        on_section_complete=on_section_complete,
    )
    return PipelineRunResult(
        document_markdown=core_result.document_markdown,
        step_results=[
            PipelineStepResult(
                step=item.step,
                duration_ms=item.duration_ms,
                metadata=_enrich_step_metadata(item.step, item.metadata, resolved_route),
            )
            for item in core_result.step_results
        ],
    )


def _enrich_step_metadata(
    step: str,
    metadata: dict[str, object],
    resolved_route: ResolvedGenerationRoute,
) -> dict[str, object]:
    if step != "generation":
        return metadata
    enriched = dict(metadata)
    enriched.update(resolved_route.metadata())
    return enriched


__all__ = [
    "PIPELINE_STEP_LABELS",
    "PipelineRunResult",
    "PipelineStepResult",
    "build_model_spec",
    "parse_context_inputs",
    "run_document_pipeline",
]
