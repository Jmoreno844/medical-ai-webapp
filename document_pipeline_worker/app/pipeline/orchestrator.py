from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from classification.classify import run_classification_session
from classification.lib import load_prompt as load_classification_prompt
from clustering.cluster import run_clustering_with_repair
from clustering.lib import enrich_clustering_result_for_export, load_prompt as load_clustering_prompt
from common.context_claims import ClaimAssignment, ClinicalClaim
from common.providers import ModelSpec, default_model_for_provider, normalize_provider_name
from common.templates import ClinicalTemplate
from common.transcripts import TranscriptCase, build_turn_catalog
from context_pipeline.classify_claims.classify_claims import run_classify_claims_session
from context_pipeline.classify_claims.lib import load_prompt as load_classify_claims_prompt
from context_pipeline.decompose.decompose import run_decompose
from context_pipeline.decompose.lib import DoctorNoteCase, load_prompt as load_decompose_prompt
from filtering.filter import run_filtering
from filtering.lib import FilteringResult, load_prompt as load_filtering_prompt
from generation.generate import run_generation_session
from generation.lib import load_prompt as load_generation_prompt
from generation.lib import render_generated_section_markdown

from app.pipeline.bridge import (
    apply_filtering_to_transcript,
    assignments_from_classification_session,
    clusters_from_clustering_result,
    transcript_case_from_filtering,
)
from app.pipeline.config import PipelineConfig, StepConfig


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


def build_model_spec(config: StepConfig) -> ModelSpec:
    provider = normalize_provider_name(config.provider)
    model = (config.model.strip() or default_model_for_provider(provider)).strip()
    return ModelSpec(alias=provider, provider=provider, model=model)


def _has_meaningful_context(context_content: str) -> bool:
    normalized = context_content.strip().lower()
    if not normalized:
        return False
    return normalized not in {"no se agregó contexto.", "no se agrego contexto."}


def run_context_from_doctor_note(
    *,
    session_id: str,
    context_content: str,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    decompose_prompt_version: str,
    classify_prompt_version: str,
) -> tuple[list[ClaimAssignment], dict[str, ClinicalClaim]]:
    decompose_prompt = load_decompose_prompt(decompose_prompt_version)
    classify_prompt = load_classify_claims_prompt(classify_prompt_version)
    doctor_case = DoctorNoteCase(session_id=session_id, doctor_note=context_content)
    doctor_claims, _ = run_decompose(
        case=doctor_case,
        model_spec=model_spec,
        system_prompt=decompose_prompt,
    )
    if not doctor_claims:
        return [], {}
    classification_result, _ = run_classify_claims_session(
        claims=doctor_claims,
        template=template,
        model_spec=model_spec,
        system_prompt=classify_prompt,
    )
    claims_by_id = {claim.claim_id: claim for claim in doctor_claims}
    return classification_result.assignments, claims_by_id


def run_document_pipeline(
    *,
    session_id: str,
    template: ClinicalTemplate,
    transcript_json: dict[str, object],
    context_content: str,
    pipeline_config: PipelineConfig,
    on_step_complete: Callable[[str, dict[str, object]], None] | None = None,
    on_section_complete: Callable[[str, str, str], None] | None = None,
) -> PipelineRunResult:
    import time

    step_results: list[PipelineStepResult] = []
    base_case = TranscriptCase(id=session_id, transcript_json=transcript_json)
    catalog = build_turn_catalog(transcript_json)

    def _notify_step(step: str, metadata: dict[str, object], started_at: float) -> None:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        step_results.append(PipelineStepResult(step=step, duration_ms=duration_ms, metadata=metadata))
        if on_step_complete is not None:
            on_step_complete(step, {**metadata, "duration_ms": duration_ms})

    # filtering
    filtering_cfg = pipeline_config.step_config("filtering")
    filtering_spec = build_model_spec(filtering_cfg)
    filtering_prompt = load_filtering_prompt(filtering_cfg.prompt_version)
    started = time.perf_counter()
    filtering_result, filtering_llm = run_filtering(
        case=base_case,
        model_spec=filtering_spec,
        system_prompt=filtering_prompt,
    )
    _notify_step(
        "filtering",
        {
            "strategy": filtering_cfg.strategy,
            "prompt_version": filtering_cfg.prompt_version,
            "provider": filtering_spec.provider,
            "model": filtering_spec.model,
            "turn_count": len(catalog),
            "drop_count": len(filtering_result.drop_turn_ids),
            "usage": filtering_llm.usage,
        },
        started,
    )

    clustering_case = transcript_case_from_filtering(
        base_case=base_case,
        drop_turn_ids=filtering_result.drop_turn_ids,
    )

    # clustering
    clustering_cfg = pipeline_config.step_config("clustering")
    clustering_spec = build_model_spec(clustering_cfg)
    clustering_prompt = load_clustering_prompt(clustering_cfg.prompt_version)
    started = time.perf_counter()
    clustering_run = run_clustering_with_repair(
        case=clustering_case,
        model_spec=clustering_spec,
        system_prompt=clustering_prompt,
        require_complete_coverage=True,
    )
    filtered_catalog = build_turn_catalog(clustering_case.transcript_json)
    clustering_export = enrich_clustering_result_for_export(
        clustering_run.result,
        filtered_catalog,
    )
    _notify_step(
        "clustering",
        {
            "strategy": clustering_cfg.strategy,
            "prompt_version": clustering_cfg.prompt_version,
            "provider": clustering_spec.provider,
            "model": clustering_spec.model,
            "cluster_count": len(clustering_run.result.clusters),
            "repair_pass_count": len(clustering_run.repair_passes),
            "usage": clustering_run.llm_response.usage,
        },
        started,
    )

    clusters = clusters_from_clustering_result(
        clustering_export,
        session_id=session_id,
        template_id=template.id,
    )

    # classification
    classification_cfg = pipeline_config.step_config("classification")
    classification_spec = build_model_spec(classification_cfg)
    classification_prompt = load_classification_prompt(classification_cfg.prompt_version)
    started = time.perf_counter()
    classification_run = run_classification_session(
        session_id=session_id,
        clusters=clusters,
        template=template,
        model_spec=classification_spec,
        system_prompt=classification_prompt,
    )
    session_result = classification_run.session_result.model_dump()
    _notify_step(
        "classification",
        {
            "strategy": classification_cfg.strategy,
            "prompt_version": classification_cfg.prompt_version,
            "provider": classification_spec.provider,
            "model": classification_spec.model,
            "assignment_count": len(classification_run.session_result.assignments),
            "usage": classification_run.llm_usage_summary,
        },
        started,
    )

    assignments = assignments_from_classification_session(session_result)

    claim_assignments: list[ClaimAssignment] | None = None
    claims_by_id: dict[str, ClinicalClaim] | None = None
    if pipeline_config.context_enabled and _has_meaningful_context(context_content):
        context_cfg = pipeline_config.step_config("context")
        context_spec = build_model_spec(context_cfg)
        started = time.perf_counter()
        claim_assignments, claims_by_id = run_context_from_doctor_note(
            session_id=session_id,
            context_content=context_content,
            template=template,
            model_spec=context_spec,
            decompose_prompt_version=pipeline_config.context_decompose_prompt_version,
            classify_prompt_version=pipeline_config.context_classify_prompt_version,
        )
        _notify_step(
            "context",
            {
                "strategy": context_cfg.strategy,
                "provider": context_spec.provider,
                "model": context_spec.model,
                "claim_count": len(claims_by_id),
                "assignment_count": len(claim_assignments),
            },
            started,
        )

    # generation
    generation_cfg = pipeline_config.step_config("generation")
    generation_spec = build_model_spec(generation_cfg)
    generation_prompt = load_generation_prompt(generation_cfg.prompt_version)
    started = time.perf_counter()
    generation_run = run_generation_session(
        session_id=session_id,
        assignments=assignments,
        clusters=clusters,
        template=template,
        model_spec=generation_spec,
        system_prompt=generation_prompt,
        section_concurrency=pipeline_config.generation_section_concurrency,
        claim_assignments=claim_assignments,
        claims_by_id=claims_by_id,
    )
    _notify_step(
        "generation",
        {
            "strategy": generation_cfg.strategy,
            "prompt_version": generation_cfg.prompt_version,
            "provider": generation_spec.provider,
            "model": generation_spec.model,
            "section_count": len(generation_run.session_result.sections),
            "usage": generation_run.llm_usage_summary,
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
        if on_section_complete is not None:
            on_section_complete(section_result.section_id, heading, section_md)

    document_markdown = "\n".join(markdown_parts).strip()
    return PipelineRunResult(document_markdown=document_markdown, step_results=step_results)
