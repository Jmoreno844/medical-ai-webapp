from __future__ import annotations

from common.context_spans import (
    FilterSpansResult,
    Span,
    SpanKind,
)
from context_pipeline.filter_audit import (
    compute_directive_filter_metrics,
    compute_document_filter_pipeline_counts,
    enrich_document_directive_filter_for_export,
    spans_after_filter_spans,
)


def _span(span_id: str, *, doc: str = "doc_a") -> Span:
    return Span(id=span_id, doc=doc, kind=SpanKind.LINE, text=f"text-{span_id}")


def test_spans_after_filter_spans_drops_ids_from_filter_result() -> None:
    document_spans = [_span("1"), _span("2"), _span("3")]
    result = FilterSpansResult(drop_ids=["2"])
    kept = spans_after_filter_spans(document_spans, result)
    assert [span.id for span in kept] == ["1", "3"]


def test_compute_document_filter_pipeline_counts_per_stage() -> None:
    document_spans = [_span("1"), _span("2"), _span("3")]
    filter_result = FilterSpansResult(drop_ids=["2"])
    directive_output = [_span("1")]

    counts = compute_document_filter_pipeline_counts(
        document_spans=document_spans,
        filter_result=filter_result,
        directive_output_spans=directive_output,
    )

    assert counts["filter_spans"] == {
        "input_span_count": 3,
        "drop_count": 1,
        "kept_span_count": 2,
        "drop_ids": ["2"],
    }
    assert counts["document_directive_filter"] == {
        "input_span_count": 2,
        "kept_span_count": 1,
        "drop_count": 1,
        "drop_ids": ["3"],
        "kept_ids": ["1"],
    }


def test_compute_directive_filter_metrics_without_drops() -> None:
    spans = [_span("1"), _span("2")]
    metrics = compute_directive_filter_metrics(spans, spans)
    assert metrics["drop_count"] == 0
    assert metrics["kept_ids"] == ["1", "2"]


def test_enrich_document_directive_filter_for_export_includes_counts() -> None:
    input_spans = [_span("1"), _span("2")]
    output_spans = [_span("2")]
    export = enrich_document_directive_filter_for_export(
        input_spans=input_spans,
        output_spans=output_spans,
        ambiguous_directives=[],
        selector_result_count=0,
    )
    assert export["input_span_count"] == 2
    assert export["kept_span_count"] == 1
    assert export["drop_count"] == 1
    assert export["drop_ids"] == ["1"]
    assert export["kept_ids"] == ["2"]
    assert export["selector_result_count"] == 0
