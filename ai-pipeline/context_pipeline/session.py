from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from common.context_spans import (
    ClassifyClustersResult,
    Directive,
    DoctorItem,
    FilterSpansResult,
    SectionContext,
    Span,
    SpanCluster,
    TriageResult,
    apply_span_drops,
    build_adapter_jobs,
    build_spans_from_pdf,
    build_spans_from_text,
    doctor_items_to_spans,
    merge_spans,
    propagate_cluster_date_hints,
    split_doctor_items,
)
from common.llm_response import LlmResponse
from common.providers import ModelSpec
from common.templates import ClinicalTemplate, load_template
from context_pipeline.cases.lib import (
    ContextCase,
    load_context_case,
    load_context_cases,
    load_document_text,
    select_context_case,
)
from context_pipeline.classify_clusters.classify_clusters import run_classify_clusters
from context_pipeline.cluster_spans.cluster_spans import run_cluster_spans
from context_pipeline.filter_spans.filter_spans import run_filter_spans
from context_pipeline.section_adapter.lib import run_section_adapter_session
from context_pipeline.triage.triage import run_triage


@dataclass(frozen=True, slots=True)
class ContextLlmCall:
    label: str
    provider: str
    model: str
    llm_response: LlmResponse


@dataclass(frozen=True, slots=True)
class ContextPipelineRun:
    session_id: str
    template_id: str
    encounter_date: str | None
    doctor_items: list[DoctorItem]
    is_pasted: bool
    triage_result: TriageResult
    directives: list[Directive]
    span_pool: list[Span]
    filtered_spans: list[Span]
    clusters: list[SpanCluster]
    classify_result: ClassifyClustersResult
    adapter_jobs: dict[str, list[str]]
    section_context: SectionContext
    llm_calls: list[ContextLlmCall]
    filter_result: FilterSpansResult | None = None
    stopped_after_step: str | None = None
    pipeline_error: str | None = None


def _build_span_pool(
    *,
    context_case: ContextCase,
    cases_dir: Path,
    doctor_items: list[DoctorItem],
    triage_result: TriageResult,
    is_pasted: bool,
    include_doctor_note: bool,
    include_documents: bool,
) -> list[Span]:
    span_lists: list[list[Span]] = []

    if include_doctor_note:
        if is_pasted:
            span_lists.append(
                build_spans_from_text(
                    context_case.doctor_note.doctor_note,
                    doc="nota_medico",
                    session_id=context_case.meta.session_id,
                )
            )
        else:
            span_lists.append(
                doctor_items_to_spans(doctor_items, triage_result.content_ids)
            )

    if include_documents:
        for fixture in context_case.document_fixtures:
            source_path = (cases_dir / fixture.source_file).resolve()
            if source_path.suffix.lower() == ".pdf":
                spans = build_spans_from_pdf(
                    source_path,
                    doc=fixture.document_id,
                    session_id=context_case.meta.session_id,
                )
            else:
                spans = build_spans_from_text(
                    load_document_text(fixture, cases_dir=cases_dir),
                    doc=fixture.document_id,
                    session_id=context_case.meta.session_id,
                )
            span_lists.append(spans)

    if not span_lists:
        return []
    return merge_spans(*span_lists)


def _primary_document_date(context_case: ContextCase) -> str | None:
    for fixture in context_case.document_fixtures:
        if fixture.document_date:
            return fixture.document_date
    return None


def _partial_pipeline_run(
    *,
    session_id: str,
    template_id: str,
    encounter_date: str | None,
    doctor_items: list[DoctorItem],
    is_pasted: bool,
    triage_result: TriageResult,
    span_pool: list[Span],
    filter_result: FilterSpansResult,
    filtered_spans: list[Span],
    stopped_after_step: str,
    pipeline_error: str,
    llm_calls: list[ContextLlmCall],
) -> ContextPipelineRun:
    return ContextPipelineRun(
        session_id=session_id,
        template_id=template_id,
        encounter_date=encounter_date,
        doctor_items=doctor_items,
        is_pasted=is_pasted,
        triage_result=triage_result,
        directives=triage_result.directives,
        span_pool=span_pool,
        filtered_spans=filtered_spans,
        clusters=[],
        classify_result=ClassifyClustersResult(),
        adapter_jobs={},
        section_context={},
        llm_calls=llm_calls,
        filter_result=filter_result,
        stopped_after_step=stopped_after_step,
        pipeline_error=pipeline_error,
    )


def _build_ad_hoc_span_pool(
    *,
    session_id: str,
    doctor_note: str | None,
    doctor_items: list[DoctorItem],
    triage_result: TriageResult,
    is_pasted: bool,
    include_doctor_note: bool,
    document_pdf_path: Path | None,
    document_id: str,
) -> list[Span]:
    span_lists: list[list[Span]] = []

    if include_doctor_note and doctor_note and doctor_note.strip():
        if is_pasted:
            span_lists.append(
                build_spans_from_text(
                    doctor_note.strip(),
                    doc="nota_medico",
                    session_id=session_id,
                )
            )
        else:
            span_lists.append(
                doctor_items_to_spans(doctor_items, triage_result.content_ids)
            )

    if document_pdf_path is not None:
        span_lists.append(
            build_spans_from_pdf(
                document_pdf_path,
                doc=document_id,
                session_id=session_id,
            )
        )

    if not span_lists:
        return []
    return merge_spans(*span_lists)


def _run_context_pipeline_core(
    *,
    session_id: str,
    template: ClinicalTemplate,
    template_id: str,
    encounter_date: str | None,
    document_date: str | None,
    doctor_items: list[DoctorItem],
    is_pasted: bool,
    triage_result: TriageResult,
    span_pool: list[Span],
    model_spec: ModelSpec,
    filter_spans_prompt: str,
    filter_spans_prompt_version: str = "v001",
    cluster_spans_prompt: str,
    cluster_spans_prompt_version: str = "v001",
    classify_clusters_prompt: str,
    classify_clusters_prompt_version: str = "v001",
    section_adapter_prompt: str,
    section_adapter_prompt_version: str = "v001",
    llm_calls: list[ContextLlmCall],
) -> ContextPipelineRun:
    if not span_pool:
        raise ValueError(
            "context_pipeline_requires_at_least_one_span_source: "
            "provide doctor note and/or document"
        )

    filter_result, filter_response = run_filter_spans(
        encounter_date=encounter_date,
        document_date=document_date,
        directives=triage_result.directives,
        spans=span_pool,
        model_spec=model_spec,
        system_prompt=filter_spans_prompt,
        prompt_version=filter_spans_prompt_version,
    )
    llm_calls.append(
        ContextLlmCall(
            label="filter_spans",
            provider=model_spec.provider,
            model=model_spec.model,
            llm_response=filter_response,
        )
    )
    filtered_spans = apply_span_drops(span_pool, filter_result.drop_ids)
    if not filtered_spans:
        return _partial_pipeline_run(
            session_id=session_id,
            template_id=template_id,
            encounter_date=encounter_date,
            doctor_items=doctor_items,
            is_pasted=is_pasted,
            triage_result=triage_result,
            span_pool=span_pool,
            filter_result=filter_result,
            filtered_spans=filtered_spans,
            stopped_after_step="filter_spans",
            pipeline_error="context_pipeline_no_spans_after_filter",
            llm_calls=llm_calls,
        )

    clusters, cluster_response = run_cluster_spans(
        spans=filtered_spans,
        model_spec=model_spec,
        system_prompt=cluster_spans_prompt,
        prompt_version=cluster_spans_prompt_version,
    )
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
        system_prompt=classify_clusters_prompt,
        encounter_date=encounter_date,
        document_date=document_date,
        prompt_version=classify_clusters_prompt_version,
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
        directives=triage_result.directives,
        model_spec=model_spec,
        system_prompt=section_adapter_prompt,
        prompt_version=section_adapter_prompt_version,
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
        span_pool=span_pool,
        filtered_spans=filtered_spans,
        clusters=clusters,
        classify_result=classify_result,
        adapter_jobs=adapter_jobs,
        section_context=adapter_session.section_context,
        llm_calls=llm_calls,
        filter_result=filter_result,
    )


def run_context_pipeline_ad_hoc(
    *,
    session_id: str,
    template_id: str,
    templates_dir: Path,
    model_spec: ModelSpec,
    triage_prompt: str,
    filter_spans_prompt: str,
    filter_spans_prompt_version: str = "v001",
    cluster_spans_prompt: str,
    cluster_spans_prompt_version: str = "v001",
    classify_clusters_prompt: str,
    classify_clusters_prompt_version: str = "v001",
    section_adapter_prompt: str,
    section_adapter_prompt_version: str = "v001",
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
            system_prompt=triage_prompt,
        )
        llm_calls.append(
            ContextLlmCall(
                label="triage",
                provider=model_spec.provider,
                model=model_spec.model,
                llm_response=triage_response,
            )
        )

    span_pool = _build_ad_hoc_span_pool(
        session_id=session_id,
        doctor_note=doctor_note.strip() if has_note else None,
        doctor_items=doctor_items,
        triage_result=triage_result,
        is_pasted=is_pasted,
        include_doctor_note=has_note,
        document_pdf_path=document_pdf_path,
        document_id=document_id,
    )

    return _run_context_pipeline_core(
        session_id=session_id,
        template=template,
        template_id=template_id,
        encounter_date=encounter_date,
        document_date=document_date,
        doctor_items=doctor_items,
        is_pasted=is_pasted,
        triage_result=triage_result,
        span_pool=span_pool,
        model_spec=model_spec,
        filter_spans_prompt=filter_spans_prompt,
        filter_spans_prompt_version=filter_spans_prompt_version,
        cluster_spans_prompt=cluster_spans_prompt,
        cluster_spans_prompt_version=cluster_spans_prompt_version,
        classify_clusters_prompt=classify_clusters_prompt,
        classify_clusters_prompt_version=classify_clusters_prompt_version,
        section_adapter_prompt=section_adapter_prompt,
        section_adapter_prompt_version=section_adapter_prompt_version,
        llm_calls=llm_calls,
    )


def run_context_pipeline_session(
    *,
    case_id: str,
    cases_index: Path,
    templates_dir: Path,
    model_spec: ModelSpec,
    triage_prompt: str,
    filter_spans_prompt: str,
    filter_spans_prompt_version: str = "v001",
    cluster_spans_prompt: str,
    cluster_spans_prompt_version: str = "v001",
    classify_clusters_prompt: str,
    classify_clusters_prompt_version: str = "v001",
    section_adapter_prompt: str,
    section_adapter_prompt_version: str = "v001",
    include_doctor_note: bool = True,
    include_documents: bool = True,
) -> ContextPipelineRun:
    case_meta = select_context_case(load_context_cases(cases_index), case_id=case_id)
    context_case = load_context_case(case_meta, cases_dir=cases_index.parent)
    template = load_template(case_meta.template_id, templates_dir=templates_dir)
    llm_calls: list[ContextLlmCall] = []

    doctor_items, is_pasted = split_doctor_items(
        context_case.doctor_note.doctor_note,
        session_id=case_meta.session_id,
    )
    if include_doctor_note and not doctor_items:
        raise ValueError("context_pipeline_requires_doctor_note_items")

    triage_result = TriageResult()
    if include_doctor_note:
        triage_result, triage_response = run_triage(
            session_id=case_meta.session_id,
            items=doctor_items,
            model_spec=model_spec,
            system_prompt=triage_prompt,
        )
        llm_calls.append(
            ContextLlmCall(
                label="triage",
                provider=model_spec.provider,
                model=model_spec.model,
                llm_response=triage_response,
            )
        )

    span_pool = _build_span_pool(
        context_case=context_case,
        cases_dir=cases_index.parent,
        doctor_items=doctor_items,
        triage_result=triage_result,
        is_pasted=is_pasted,
        include_doctor_note=include_doctor_note,
        include_documents=include_documents,
    )

    return _run_context_pipeline_core(
        session_id=case_meta.session_id,
        template=template,
        template_id=case_meta.template_id,
        encounter_date=case_meta.encounter_date,
        document_date=_primary_document_date(context_case),
        doctor_items=doctor_items,
        is_pasted=is_pasted,
        triage_result=triage_result,
        span_pool=span_pool,
        model_spec=model_spec,
        filter_spans_prompt=filter_spans_prompt,
        filter_spans_prompt_version=filter_spans_prompt_version,
        cluster_spans_prompt=cluster_spans_prompt,
        cluster_spans_prompt_version=cluster_spans_prompt_version,
        classify_clusters_prompt=classify_clusters_prompt,
        classify_clusters_prompt_version=classify_clusters_prompt_version,
        section_adapter_prompt=section_adapter_prompt,
        section_adapter_prompt_version=section_adapter_prompt_version,
        llm_calls=llm_calls,
    )


__all__ = [
    "ContextLlmCall",
    "ContextPipelineRun",
    "run_context_pipeline_ad_hoc",
    "run_context_pipeline_session",
]
