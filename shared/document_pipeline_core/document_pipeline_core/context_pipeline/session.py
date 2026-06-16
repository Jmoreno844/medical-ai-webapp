from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from document_pipeline_core.common.context_spans import (
    AmbiguousDirective,
    ClassifyClustersResult,
    Directive,
    DoctorItem,
    FilterSpansResult,
    SectionContext,
    SectionEvidence,
    Span,
    SpanCluster,
    TriageResult,
    build_adapter_jobs,
    document_preference_directives,
    propagate_cluster_date_hints,
    split_doctor_items,
)
from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import ModelSpec
from document_pipeline_core.common.templates import ClinicalTemplate, load_template
from document_pipeline_core.context_pipeline.config import ContextPipelinePromptBundle
from document_pipeline_core.context_pipeline.classify_clusters.classify_clusters import run_classify_clusters
from document_pipeline_core.context_pipeline.cluster_spans.cluster_spans import run_cluster_spans
from document_pipeline_core.context_pipeline.cluster_spans.lib import ClusterSpansValidationError
from document_pipeline_core.context_pipeline.document_directive_filter.document_directive_filter import (
    run_document_directive_filter,
)
from document_pipeline_core.context_pipeline.section_adapter.lib import run_section_adapter_session
from document_pipeline_core.context_pipeline.span_pool import (
    ContextSpanPools,
    build_context_span_pools_ad_hoc,
    build_context_span_pools_from_case,
    filter_document_spans,
    merge_approved_and_filtered_document_spans,
)
from document_pipeline_core.context_pipeline.triage.triage import run_triage


def _document_ids_from_spans(spans: list[Span]) -> list[str]:
    return sorted(
        {
            span.doc
            for span in spans
            if span.doc and span.doc != "nota_medico"
        }
    )


@dataclass(frozen=True, slots=True)
class ContextLlmCall:
    label: str
    provider: str
    model: str
    llm_response: LlmResponse


class ContextPipelinePartialError(Exception):
    def __init__(
        self,
        message: str,
        *,
        failed_step: str,
        partial_run: "ContextPipelineRun",
        diagnostics: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.failed_step = failed_step
        self.partial_run = partial_run
        self.diagnostics = dict(diagnostics or {})

    def diagnostics_payload(self) -> dict[str, object]:
        return dict(self.diagnostics)


@dataclass(frozen=True, slots=True)
class ContextPipelineRun:
    session_id: str
    template_id: str
    encounter_date: str | None
    doctor_items: list[DoctorItem]
    is_pasted: bool
    triage_result: TriageResult
    directives: list[Directive]
    approved_note_spans: list[Span]
    document_spans: list[Span]
    span_pool: list[Span]
    filtered_spans: list[Span]
    clusters: list[SpanCluster]
    classify_result: ClassifyClustersResult
    adapter_jobs: dict[str, list[str]]
    section_context: SectionContext
    section_evidence: SectionEvidence
    llm_calls: list[ContextLlmCall]
    filter_result: FilterSpansResult | None = None
    filter_spans_document_spans: list[Span] = field(default_factory=list)
    directive_filtered_document_spans: list[Span] = field(default_factory=list)
    ambiguous_directives: list[AmbiguousDirective] = field(default_factory=list)
    stopped_after_step: str | None = None
    pipeline_error: str | None = None


def _partial_pipeline_run(
    *,
    session_id: str,
    template_id: str,
    encounter_date: str | None,
    doctor_items: list[DoctorItem],
    is_pasted: bool,
    triage_result: TriageResult,
    span_pools: ContextSpanPools,
    span_pool: list[Span],
    filter_result: FilterSpansResult,
    filtered_spans: list[Span],
    stopped_after_step: str,
    pipeline_error: str,
    llm_calls: list[ContextLlmCall],
    ambiguous_directives: list[AmbiguousDirective] | None = None,
    filter_spans_document_spans: list[Span] | None = None,
    directive_filtered_document_spans: list[Span] | None = None,
    clusters: list[SpanCluster] | None = None,
) -> ContextPipelineRun:
    return ContextPipelineRun(
        session_id=session_id,
        template_id=template_id,
        encounter_date=encounter_date,
        doctor_items=doctor_items,
        is_pasted=is_pasted,
        triage_result=triage_result,
        directives=triage_result.directives,
        approved_note_spans=span_pools.approved_note_spans,
        document_spans=span_pools.document_spans,
        span_pool=span_pool,
        filtered_spans=filtered_spans,
        clusters=list(clusters or []),
        classify_result=ClassifyClustersResult(),
        adapter_jobs={},
        section_context={},
        section_evidence={},
        llm_calls=llm_calls,
        filter_result=filter_result,
        filter_spans_document_spans=list(filter_spans_document_spans or []),
        directive_filtered_document_spans=list(directive_filtered_document_spans or []),
        ambiguous_directives=list(ambiguous_directives or []),
        stopped_after_step=stopped_after_step,
        pipeline_error=pipeline_error,
    )


def run_context_pipeline_core(
    *,
    session_id: str,
    template: ClinicalTemplate,
    template_id: str,
    encounter_date: str | None,
    document_date: str | None,
    doctor_items: list[DoctorItem],
    is_pasted: bool,
    triage_result: TriageResult,
    span_pools: ContextSpanPools,
    model_spec: ModelSpec,
    prompt_bundle: ContextPipelinePromptBundle,
    llm_calls: list[ContextLlmCall],
) -> ContextPipelineRun:
    span_pool = span_pools.span_pool
    if not span_pool:
        raise ValueError(
            "context_pipeline_requires_at_least_one_span_source: "
            "provide doctor note and/or document"
        )

    filtered_documents = filter_document_spans(
        document_spans=span_pools.document_spans,
        encounter_date=encounter_date,
        document_date=document_date,
        directives=[],
        model_spec=model_spec,
        system_prompt=prompt_bundle.filter_spans.system_prompt,
        prompt_version=prompt_bundle.filter_spans.prompt_version,
    )
    if filtered_documents.llm_response is not None:
        llm_calls.append(
            ContextLlmCall(
                label="filter_spans",
                provider=model_spec.provider,
                model=model_spec.model,
                llm_response=filtered_documents.llm_response,
            )
        )

    available_documents = _document_ids_from_spans(span_pools.document_spans)
    directive_filter_outcome, directive_filter_responses = run_document_directive_filter(
        spans=filtered_documents.filtered_document_spans,
        directives=triage_result.directives,
        available_documents=available_documents,
        model_spec=model_spec,
        system_prompt=prompt_bundle.document_directive_filter.system_prompt,
        prompt_version=prompt_bundle.document_directive_filter.prompt_version,
    )
    for index, llm_response in enumerate(directive_filter_responses, start=1):
        llm_calls.append(
            ContextLlmCall(
                label=f"document_directive_filter:{index}",
                provider=model_spec.provider,
                model=model_spec.model,
                llm_response=llm_response,
            )
        )

    filtered_spans = merge_approved_and_filtered_document_spans(
        approved_note_spans=span_pools.approved_note_spans,
        filtered_document_spans=directive_filter_outcome.spans,
    )
    if not filtered_spans:
        filter_result = filtered_documents.filter_result or FilterSpansResult(drop_ids=[])
        return _partial_pipeline_run(
            session_id=session_id,
            template_id=template_id,
            encounter_date=encounter_date,
            doctor_items=doctor_items,
            is_pasted=is_pasted,
            triage_result=triage_result,
            span_pools=span_pools,
            span_pool=span_pool,
            filter_result=filter_result,
            filtered_spans=filtered_spans,
            ambiguous_directives=directive_filter_outcome.ambiguous_directives,
            filter_spans_document_spans=filtered_documents.filtered_document_spans,
            directive_filtered_document_spans=directive_filter_outcome.spans,
            stopped_after_step="document_directive_filter",
            pipeline_error="context_pipeline_no_spans_after_filter",
            llm_calls=llm_calls,
        )

    try:
        clusters, cluster_response = run_cluster_spans(
            spans=filtered_spans,
            model_spec=model_spec,
            system_prompt=prompt_bundle.cluster_spans.system_prompt,
            prompt_version=prompt_bundle.cluster_spans.prompt_version,
        )
    except ClusterSpansValidationError as exc:
        if exc.llm_response is not None:
            llm_calls.append(
                ContextLlmCall(
                    label="cluster_spans",
                    provider=model_spec.provider,
                    model=model_spec.model,
                    llm_response=exc.llm_response,
                )
            )
        raise ContextPipelinePartialError(
            str(exc),
            failed_step="cluster_spans",
            partial_run=_partial_pipeline_run(
                session_id=session_id,
                template_id=template_id,
                encounter_date=encounter_date,
                doctor_items=doctor_items,
                is_pasted=is_pasted,
                triage_result=triage_result,
                span_pools=span_pools,
                span_pool=span_pool,
                filter_result=filtered_documents.filter_result,
                filtered_spans=filtered_spans,
                ambiguous_directives=directive_filter_outcome.ambiguous_directives,
                filter_spans_document_spans=filtered_documents.filtered_document_spans,
                directive_filtered_document_spans=directive_filter_outcome.spans,
                clusters=exc.clusters,
                stopped_after_step="cluster_spans",
                pipeline_error=str(exc),
                llm_calls=llm_calls,
            ),
            diagnostics=exc.diagnostics(),
        ) from exc
    llm_calls.append(
        ContextLlmCall(
            label="cluster_spans",
            provider=model_spec.provider,
            model=model_spec.model,
            llm_response=cluster_response,
        )
    )
    clusters = propagate_cluster_date_hints(clusters, filtered_spans)

    classify_result, classify_response = run_classify_clusters(
        template=template,
        clusters=clusters,
        spans=filtered_spans,
        model_spec=model_spec,
        system_prompt=prompt_bundle.classify_clusters.system_prompt,
        encounter_date=encounter_date,
        document_date=document_date,
        prompt_version=prompt_bundle.classify_clusters.prompt_version,
    )
    llm_calls.append(
        ContextLlmCall(
            label="classify_clusters",
            provider=model_spec.provider,
            model=model_spec.model,
            llm_response=classify_response,
        )
    )

    adapter_jobs = build_adapter_jobs(classify_result, template.section_id_set())
    adapter_session = run_section_adapter_session(
        adapter_jobs=adapter_jobs,
        clusters=clusters,
        spans=filtered_spans,
        template=template,
        encounter_date=encounter_date,
        document_date=document_date,
        directives=document_preference_directives(triage_result.directives),
        model_spec=model_spec,
        system_prompt=prompt_bundle.section_adapter.system_prompt,
        prompt_version=prompt_bundle.section_adapter.prompt_version,
    )
    for section_run in adapter_session.section_runs:
        llm_calls.append(
            ContextLlmCall(
                label=f"section_adapter:{section_run.section_id}",
                provider=model_spec.provider,
                model=model_spec.model,
                llm_response=section_run.llm_response,
            )
        )

    return ContextPipelineRun(
        session_id=session_id,
        template_id=template_id,
        encounter_date=encounter_date,
        doctor_items=doctor_items,
        is_pasted=is_pasted,
        triage_result=triage_result,
        directives=triage_result.directives,
        approved_note_spans=span_pools.approved_note_spans,
        document_spans=span_pools.document_spans,
        span_pool=span_pool,
        filtered_spans=filtered_spans,
        clusters=clusters,
        classify_result=classify_result,
        adapter_jobs=adapter_jobs,
        section_context=adapter_session.section_context,
        section_evidence=adapter_session.section_evidence,
        llm_calls=llm_calls,
        filter_result=filtered_documents.filter_result,
        filter_spans_document_spans=filtered_documents.filtered_document_spans,
        directive_filtered_document_spans=directive_filter_outcome.spans,
        ambiguous_directives=directive_filter_outcome.ambiguous_directives,
    )


def run_context_pipeline_ad_hoc(
    *,
    session_id: str,
    template_id: str,
    templates_dir: Path,
    model_spec: ModelSpec,
    prompt_bundle: ContextPipelinePromptBundle,
    doctor_note: str | None = None,
    document_pdf_path: Path | None = None,
    document_id: str = "uploaded_document",
    encounter_date: str | None = None,
    document_date: str | None = None,
) -> ContextPipelineRun:
    has_note = bool(doctor_note and doctor_note.strip())
    has_document = document_pdf_path is not None
    if not has_note and not has_document:
        raise ValueError("context_ad_hoc_requires_doctor_note_or_document")

    template = load_template(template_id, templates_dir=templates_dir)
    llm_calls: list[ContextLlmCall] = []
    available_documents = [document_id] if has_document else []
    template_section_ids = [section.section_id for section in template.sections]

    doctor_items: list[DoctorItem] = []
    is_pasted = False
    triage_result = TriageResult()

    if has_note:
        doctor_items, is_pasted = split_doctor_items(
            doctor_note.strip(),
            session_id=session_id,
        )
        if not doctor_items:
            raise ValueError("context_ad_hoc_doctor_note_has_no_items")
        triage_result, triage_response = run_triage(
            session_id=session_id,
            items=doctor_items,
            model_spec=model_spec,
            system_prompt=prompt_bundle.triage.system_prompt,
            prompt_version=prompt_bundle.triage.prompt_version,
            available_documents=available_documents,
            template_section_ids=template_section_ids,
        )
        llm_calls.append(
            ContextLlmCall(
                label="triage",
                provider=model_spec.provider,
                model=model_spec.model,
                llm_response=triage_response,
            )
        )

    span_pools = build_context_span_pools_ad_hoc(
        session_id=session_id,
        doctor_note=doctor_note.strip() if has_note else None,
        doctor_items=doctor_items,
        triage_result=triage_result,
        is_pasted=is_pasted,
        include_doctor_note=has_note,
        document_pdf_path=document_pdf_path,
        document_id=document_id,
    )

    return run_context_pipeline_core(
        session_id=session_id,
        template=template,
        template_id=template_id,
        encounter_date=encounter_date,
        document_date=document_date,
        doctor_items=doctor_items,
        is_pasted=is_pasted,
        triage_result=triage_result,
        span_pools=span_pools,
        model_spec=model_spec,
        prompt_bundle=prompt_bundle,
        llm_calls=llm_calls,
    )



__all__ = [
    "ContextLlmCall",
    "ContextPipelinePartialError",
    "ContextPipelineRun",
    "run_context_pipeline_ad_hoc",
    "run_context_pipeline_core",
]
