from __future__ import annotations

from unittest.mock import MagicMock, patch

from common.context_spans import DoctorItem, FilterSpansResult, TriageResult
from context_pipeline.span_pool import (
    build_approved_note_spans,
    filter_document_spans,
    merge_approved_and_filtered_document_spans,
)


def test_build_approved_note_spans_uses_content_ids_for_structured_note() -> None:
    items = [
        DoctorItem(id="1", text="meta"),
        DoctorItem(id="2", text="Paciente alérgico a penicilina."),
    ]
    triage = TriageResult(content_ids=["2"], drop_ids=["1"])
    spans = build_approved_note_spans(
        doctor_note_text="meta\nPaciente alérgico a penicilina.",
        session_id="case2",
        doctor_items=items,
        triage_result=triage,
        is_pasted=False,
        include_doctor_note=True,
    )
    assert len(spans) == 1
    assert spans[0].doc == "nota_medico"
    assert "penicilina" in spans[0].text


def test_filter_document_spans_skips_llm_when_no_documents() -> None:
    filtered = filter_document_spans(
        document_spans=[],
        encounter_date="2026-06-14",
        document_date=None,
        directives=[],
        model_spec=MagicMock(provider="openai", model="gpt-4.1-mini"),
        system_prompt="system",
        prompt_version="v002",
    )
    assert filtered.filter_result is None
    assert filtered.filtered_document_spans == []
    assert filtered.llm_response is None


def test_merge_keeps_note_spans_when_documents_are_all_dropped() -> None:
    from common.context_spans import Span, SpanKind

    note_spans = [
        Span(id="1", doc="nota_medico", kind=SpanKind.LINE, text="Alergia a penicilina"),
    ]
    document_spans = [
        Span(id="1", doc="epicrisis", kind=SpanKind.LINE, text="header legal"),
    ]
    merged = merge_approved_and_filtered_document_spans(
        approved_note_spans=note_spans,
        filtered_document_spans=[],
    )
    assert len(merged) == 1
    assert merged[0].text == "Alergia a penicilina"


@patch("context_pipeline.span_pool.run_filter_spans")
def test_filter_document_spans_only_receives_document_pool(
    mock_run_filter_spans: MagicMock,
) -> None:
    from common.context_spans import Span, SpanKind
    from common.llm_response import LlmResponse

    document_spans = [
        Span(id="1", doc="labs", kind=SpanKind.LINE, text="Hb 9.2"),
    ]
    mock_run_filter_spans.return_value = (
        FilterSpansResult(drop_ids=[]),
        LlmResponse(content="{}"),
    )

    filter_document_spans(
        document_spans=document_spans,
        encounter_date=None,
        document_date=None,
        directives=[],
        model_spec=MagicMock(provider="openai", model="gpt-4.1-mini"),
        system_prompt="system",
        prompt_version="v002",
    )

    assert mock_run_filter_spans.call_args.kwargs["spans"] == document_spans
