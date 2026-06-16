from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from document_pipeline_core.common.context_spans import (
    Directive,
    DoctorItem,
    FilterSpansResult,
    Span,
    TriageResult,
    apply_span_drops,
    build_spans_from_pdf,
    build_spans_from_text,
    doctor_items_to_spans,
    merge_spans,
)
from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import ModelSpec
from document_pipeline_core.context_pipeline.fixtures import (
    ContextCase,
    DocumentFixture,
    load_document_text,
)
from document_pipeline_core.context_pipeline.filter_spans.filter_spans import run_filter_spans


@dataclass(frozen=True, slots=True)
class ContextSpanPools:
    approved_note_spans: list[Span]
    document_spans: list[Span]

    @property
    def span_pool(self) -> list[Span]:
        parts: list[list[Span]] = []
        if self.approved_note_spans:
            parts.append(self.approved_note_spans)
        if self.document_spans:
            parts.append(self.document_spans)
        if not parts:
            return []
        return merge_spans(*parts)


@dataclass(frozen=True, slots=True)
class FilteredDocumentSpans:
    filter_result: FilterSpansResult | None
    filtered_document_spans: list[Span]
    llm_response: LlmResponse | None


def build_approved_note_spans(
    *,
    doctor_note_text: str,
    session_id: str,
    doctor_items: list[DoctorItem],
    triage_result: TriageResult,
    is_pasted: bool,
    include_doctor_note: bool,
) -> list[Span]:
    if not include_doctor_note:
        return []
    normalized_note = doctor_note_text.strip()
    if not normalized_note:
        return []
    if is_pasted:
        return build_spans_from_text(
            normalized_note,
            doc="nota_medico",
            session_id=session_id,
        )
    return doctor_items_to_spans(doctor_items, triage_result.content_ids)


def _build_document_spans_from_fixtures(
    *,
    fixtures: list[DocumentFixture],
    cases_dir: Path,
    session_id: str,
) -> list[Span]:
    span_lists: list[list[Span]] = []
    for fixture in fixtures:
        source_path = (cases_dir / fixture.source_file).resolve()
        if source_path.suffix.lower() == ".pdf":
            spans = build_spans_from_pdf(
                source_path,
                doc=fixture.document_id,
                session_id=session_id,
            )
        else:
            spans = build_spans_from_text(
                load_document_text(fixture, cases_dir=cases_dir),
                doc=fixture.document_id,
                session_id=session_id,
            )
        span_lists.append(spans)
    if not span_lists:
        return []
    return merge_spans(*span_lists)


def build_context_span_pools_from_case(
    *,
    context_case: ContextCase,
    cases_dir: Path,
    doctor_items: list[DoctorItem],
    triage_result: TriageResult,
    is_pasted: bool,
    include_doctor_note: bool,
    include_documents: bool,
) -> ContextSpanPools:
    approved_note_spans = build_approved_note_spans(
        doctor_note_text=context_case.doctor_note.doctor_note,
        session_id=context_case.meta.session_id,
        doctor_items=doctor_items,
        triage_result=triage_result,
        is_pasted=is_pasted,
        include_doctor_note=include_doctor_note,
    )
    document_spans: list[Span] = []
    if include_documents:
        document_spans = _build_document_spans_from_fixtures(
            fixtures=context_case.document_fixtures,
            cases_dir=cases_dir,
            session_id=context_case.meta.session_id,
        )
    return ContextSpanPools(
        approved_note_spans=approved_note_spans,
        document_spans=document_spans,
    )


def build_context_span_pools_ad_hoc(
    *,
    session_id: str,
    doctor_note: str | None,
    doctor_items: list[DoctorItem],
    triage_result: TriageResult,
    is_pasted: bool,
    include_doctor_note: bool,
    document_pdf_path: Path | None,
    document_id: str,
) -> ContextSpanPools:
    approved_note_spans: list[Span] = []
    if include_doctor_note and doctor_note and doctor_note.strip():
        approved_note_spans = build_approved_note_spans(
            doctor_note_text=doctor_note,
            session_id=session_id,
            doctor_items=doctor_items,
            triage_result=triage_result,
            is_pasted=is_pasted,
            include_doctor_note=True,
        )

    document_spans: list[Span] = []
    if document_pdf_path is not None:
        document_spans = build_spans_from_pdf(
            document_pdf_path,
            doc=document_id,
            session_id=session_id,
        )

    return ContextSpanPools(
        approved_note_spans=approved_note_spans,
        document_spans=document_spans,
    )


def filter_document_spans(
    *,
    document_spans: list[Span],
    encounter_date: str | None,
    document_date: str | None,
    directives: list[Directive],
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
) -> FilteredDocumentSpans:
    if not document_spans:
        return FilteredDocumentSpans(
            filter_result=None,
            filtered_document_spans=[],
            llm_response=None,
        )

    filter_result, llm_response = run_filter_spans(
        encounter_date=encounter_date,
        document_date=document_date,
        directives=directives,
        spans=document_spans,
        model_spec=model_spec,
        system_prompt=system_prompt,
        prompt_version=prompt_version,
    )
    filtered_document_spans = apply_span_drops(document_spans, filter_result.drop_ids)
    return FilteredDocumentSpans(
        filter_result=filter_result,
        filtered_document_spans=filtered_document_spans,
        llm_response=llm_response,
    )


def merge_approved_and_filtered_document_spans(
    *,
    approved_note_spans: list[Span],
    filtered_document_spans: list[Span],
) -> list[Span]:
    parts: list[list[Span]] = []
    if approved_note_spans:
        parts.append(approved_note_spans)
    if filtered_document_spans:
        parts.append(filtered_document_spans)
    if not parts:
        return []
    return merge_spans(*parts)


__all__ = [
    "ContextSpanPools",
    "FilteredDocumentSpans",
    "build_approved_note_spans",
    "build_context_span_pools_ad_hoc",
    "build_context_span_pools_from_case",
    "filter_document_spans",
    "merge_approved_and_filtered_document_spans",
]
