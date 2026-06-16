from __future__ import annotations

from dataclasses import dataclass

from document_pipeline_core.classification.classify import run_classification_session
from document_pipeline_core.classification.lib import ClusterCase
from document_pipeline_core.clustering.cluster import run_clustering_with_repair
from document_pipeline_core.clustering.lib import enrich_clustering_result_for_export
from document_pipeline_core.common.context_inputs import ContextInputs, has_meaningful_doctor_note
from document_pipeline_core.common.context_spans import SectionContext, SectionEvidence
from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.prompt_runtime import load_system_prompt
from document_pipeline_core.common.providers import ModelSpec, default_model_for_provider, normalize_provider_name
from document_pipeline_core.common.templates import ClinicalTemplate
from document_pipeline_core.common.transcripts import TranscriptCase, build_turn_catalog
from document_pipeline_core.context_pipeline.config import (
    ContextPipelineConfig,
    ContextPipelinePromptBundle,
    build_context_pipeline_prompt_bundle,
)
from document_pipeline_core.context_pipeline.session import (
    ContextPipelinePartialError,
    ContextPipelineRun,
    run_context_pipeline_ad_hoc,
)
from document_pipeline_core.filtering.filter import run_filtering
from document_pipeline_core.generation.generate import run_generation_session
from document_pipeline_core.generation.lib import (
    ClusterAssignmentInput,
    render_generated_section_markdown,
)
from document_pipeline_core.orchestrators.bridge import (
    assignments_from_classification_session,
    clusters_from_clustering_result,
    transcript_case_from_filtering,
)
from document_pipeline_core.orchestrators.config import StepModelConfig
from document_pipeline_core.package_root import DEFAULT_TEMPLATES_DIR


@dataclass(frozen=True, slots=True)
class TranscriptPipelineResult:
    filtering_drop_turn_ids: list[int]
    clusters: list[ClusterCase]
    assignments: list[ClusterAssignmentInput]
    llm_calls: list[tuple[str, LlmResponse]]


@dataclass(frozen=True, slots=True)
class DocumentPipelineStepResult:
    step: str
    duration_ms: int
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class DocumentPipelineRunResult:
    document_markdown: str
    step_results: list[DocumentPipelineStepResult]
    context_run: ContextPipelineRun | None = None


def build_model_spec(config: StepModelConfig) -> ModelSpec:
    provider = normalize_provider_name(config.provider)
    model = (config.model.strip() or default_model_for_provider(provider)).strip()
    return ModelSpec(alias=provider, provider=provider, model=model)


def run_context_from_inputs(
    *,
    session_id: str,
    template_id: str,
    context_inputs: ContextInputs,
    model_spec: ModelSpec,
    prompt_bundle: ContextPipelinePromptBundle,
    encounter_date: str | None = None,
) -> ContextPipelineRun:
    doctor_note = (context_inputs.doctor_note_markdown or "").strip()
    if not has_meaningful_doctor_note(context_inputs):
        raise ValueError("context_pipeline_requires_meaningful_doctor_note")

    # Phase 1: external_documents=[]; PDF/GCS adapters land in phase 2.
    return run_context_pipeline_ad_hoc(
        session_id=session_id,
        template_id=template_id,
        templates_dir=DEFAULT_TEMPLATES_DIR,
        doctor_note=doctor_note,
        model_spec=model_spec,
        prompt_bundle=prompt_bundle,
        encounter_date=encounter_date,
        document_pdf_path=None,
    )


def run_transcript_pipeline(
    *,
    session_id: str,
    template: ClinicalTemplate,
    transcript_json: dict[str, object],
    filtering_config: StepModelConfig,
    clustering_config: StepModelConfig,
    classification_config: StepModelConfig,
) -> TranscriptPipelineResult:
    base_case = TranscriptCase(id=session_id, transcript_json=transcript_json)
    llm_calls: list[tuple[str, LlmResponse]] = []

    filtering_spec = build_model_spec(filtering_config)
    filtering_prompt = load_system_prompt("filtering", filtering_config.prompt_version)
    filtering_result, filtering_llm, _filtering_diagnostics = run_filtering(
        case=base_case,
        model_spec=filtering_spec,
        system_prompt=filtering_prompt,
        prompt_version=filtering_config.prompt_version,
    )
    llm_calls.append(("filtering", filtering_llm))

    clustering_case = transcript_case_from_filtering(
        base_case=base_case,
        drop_turn_ids=filtering_result.drop_turn_ids,
    )
    clustering_spec = build_model_spec(clustering_config)
    clustering_prompt = load_system_prompt("clustering", clustering_config.prompt_version)
    clustering_run = run_clustering_with_repair(
        case=clustering_case,
        model_spec=clustering_spec,
        system_prompt=clustering_prompt,
        require_complete_coverage=True,
    )
    llm_calls.append(("clustering", clustering_run.llm_response))

    filtered_catalog = build_turn_catalog(clustering_case.transcript_json)
    clustering_export = enrich_clustering_result_for_export(
        clustering_run.result,
        filtered_catalog,
    )
    clusters = clusters_from_clustering_result(
        clustering_export,
        session_id=session_id,
        template_id=template.id,
    )

    classification_spec = build_model_spec(classification_config)
    classification_prompt = load_system_prompt(
        "classification",
        classification_config.prompt_version,
    )
    classification_run = run_classification_session(
        session_id=session_id,
        clusters=clusters,
        template=template,
        model_spec=classification_spec,
        system_prompt=classification_prompt,
    )
    assignments = assignments_from_classification_session(
        classification_run.session_result.model_dump()
    )
    return TranscriptPipelineResult(
        filtering_drop_turn_ids=filtering_result.drop_turn_ids,
        clusters=clusters,
        assignments=assignments,
        llm_calls=llm_calls,
    )


def run_document_pipeline_v2(
    *,
    session_id: str,
    template: ClinicalTemplate,
    transcript_json: dict[str, object],
    context_inputs: ContextInputs,
    filtering_config: StepModelConfig,
    clustering_config: StepModelConfig,
    classification_config: StepModelConfig,
    context_config: ContextPipelineConfig,
    context_model: StepModelConfig,
    generation_config: StepModelConfig,
    generation_route: str = "direct",
    encounter_date: str | None = None,
    context_enabled: bool = True,
    section_concurrency: int = 4,
    on_step_complete: None | object = None,
    on_section_complete: None | object = None,
) -> DocumentPipelineRunResult:
    import time
    from collections.abc import Callable

    notify_step = on_step_complete if callable(on_step_complete) else None
    notify_section = on_section_complete if callable(on_section_complete) else None
    step_results: list[DocumentPipelineStepResult] = []

    def _record_step(step: str, metadata: dict[str, object], started_at: float) -> None:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        step_results.append(
            DocumentPipelineStepResult(
                step=step,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        )
        if notify_step is not None:
            notify_step(step, {**metadata, "duration_ms": duration_ms})

    started = time.perf_counter()
    transcript_result = run_transcript_pipeline(
        session_id=session_id,
        template=template,
        transcript_json=transcript_json,
        filtering_config=filtering_config,
        clustering_config=clustering_config,
        classification_config=classification_config,
    )
    _record_step(
        "filtering",
        {
            "drop_count": len(transcript_result.filtering_drop_turn_ids),
            "prompt_version": filtering_config.prompt_version,
        },
        started,
    )

    started = time.perf_counter()
    _record_step(
        "clustering",
        {
            "cluster_count": len(transcript_result.clusters),
            "prompt_version": clustering_config.prompt_version,
        },
        started,
    )

    started = time.perf_counter()
    _record_step(
        "classification",
        {
            "assignment_count": len(transcript_result.assignments),
            "prompt_version": classification_config.prompt_version,
        },
        started,
    )

    section_context: SectionContext | None = None
    section_evidence: SectionEvidence | None = None
    context_run: ContextPipelineRun | None = None

    if context_enabled and has_meaningful_doctor_note(context_inputs):
        context_spec = build_model_spec(context_model)
        prompt_bundle = build_context_pipeline_prompt_bundle(context_config)
        started = time.perf_counter()
        try:
            context_run = run_context_from_inputs(
                session_id=session_id,
                template_id=template.id,
                context_inputs=context_inputs,
                model_spec=context_spec,
                prompt_bundle=prompt_bundle,
                encounter_date=encounter_date,
            )
        except ContextPipelinePartialError as partial:
            context_run = partial.partial_run
            raise
        section_context = context_run.section_context
        section_evidence = context_run.section_evidence
        _record_step(
            "context",
            {
                "prompt_versions": prompt_bundle.versions_by_step(),
                "provider": context_spec.provider,
                "model": context_spec.model,
                "section_context_sections": len(section_context),
            },
            started,
        )

    generation_spec = build_model_spec(generation_config)
    linked_evidence_two_step = generation_route.strip().lower() == "two_step"
    generation_prompt = load_system_prompt(
        "generation_planner" if linked_evidence_two_step else "generation_direct",
        generation_config.prompt_version,
    )
    started = time.perf_counter()
    generation_run = run_generation_session(
        session_id=session_id,
        assignments=transcript_result.assignments,
        clusters=transcript_result.clusters,
        template=template,
        model_spec=generation_spec,
        system_prompt=generation_prompt,
        section_concurrency=section_concurrency,
        section_context=section_context,
        section_evidence=section_evidence,
        prompt_version=generation_config.prompt_version,
        linked_evidence_two_step=linked_evidence_two_step,
    )
    _record_step(
        "generation",
        {
            "route": generation_route,
            "prompt_version": generation_config.prompt_version,
            "section_count": len(generation_run.session_result.sections),
        },
        started,
    )

    headings = template.headings_by_section_id()
    markdown_parts: list[str] = []
    for section_result in generation_run.session_result.sections:
        heading = headings.get(section_result.section_id, section_result.section_id)
        section_md = render_generated_section_markdown(
            section_result.content,
            heading=heading,
        )
        if section_md is None:
            continue
        markdown_parts.append(section_md)
        if notify_section is not None:
            notify_section(section_result.section_id, heading, section_md)

    return DocumentPipelineRunResult(
        document_markdown="\n".join(markdown_parts).strip(),
        step_results=step_results,
        context_run=context_run,
    )


__all__ = [
    "DocumentPipelineRunResult",
    "DocumentPipelineStepResult",
    "StepModelConfig",
    "TranscriptPipelineResult",
    "build_model_spec",
    "run_context_from_inputs",
    "run_document_pipeline_v2",
    "run_transcript_pipeline",
]
