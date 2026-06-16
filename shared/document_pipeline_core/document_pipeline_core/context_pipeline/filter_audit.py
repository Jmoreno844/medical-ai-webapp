from __future__ import annotations

from document_pipeline_core.common.context_spans import (
    AmbiguousDirective,
    FilterSpansResult,
    Span,
    span_to_payload_item,
)


def spans_after_filter_spans(
    document_spans: list[Span],
    filter_result: FilterSpansResult | None,
) -> list[Span]:
    if filter_result is None:
        return list(document_spans)
    drop_set = set(filter_result.drop_ids)
    return [span for span in document_spans if span.id not in drop_set]


def compute_directive_filter_metrics(
    input_spans: list[Span],
    output_spans: list[Span],
) -> dict[str, object]:
    input_ids = {span.id for span in input_spans}
    output_id_set = {span.id for span in output_spans}
    kept_ids = [span.id for span in output_spans]
    drop_ids = sorted(input_ids - output_id_set)
    return {
        "input_span_count": len(input_spans),
        "kept_span_count": len(output_spans),
        "drop_count": len(drop_ids),
        "drop_ids": drop_ids,
        "kept_ids": kept_ids,
    }


def enrich_document_directive_filter_for_export(
    *,
    input_spans: list[Span],
    output_spans: list[Span],
    ambiguous_directives: list[AmbiguousDirective],
    selector_result_count: int,
) -> dict[str, object]:
    return {
        **compute_directive_filter_metrics(input_spans, output_spans),
        "ambiguous_directives": [
            item.model_dump(mode="json") for item in ambiguous_directives
        ],
        "selector_result_count": selector_result_count,
    }


def compute_document_filter_pipeline_counts(
    *,
    document_spans: list[Span],
    filter_result: FilterSpansResult | None,
    directive_output_spans: list[Span],
) -> dict[str, object]:
    after_filter_spans = spans_after_filter_spans(document_spans, filter_result)
    filter_drop_ids = list(filter_result.drop_ids) if filter_result else []
    return {
        "filter_spans": {
            "input_span_count": len(document_spans),
            "drop_count": len(filter_drop_ids),
            "kept_span_count": len(after_filter_spans),
            "drop_ids": filter_drop_ids,
        },
        "document_directive_filter": compute_directive_filter_metrics(
            after_filter_spans,
            directive_output_spans,
        ),
    }


def document_span_payloads_after_stages(
    *,
    document_spans: list[Span],
    filter_result: FilterSpansResult | None,
    directive_output_spans: list[Span],
) -> dict[str, list[dict[str, object]]]:
    after_filter_spans = spans_after_filter_spans(document_spans, filter_result)
    return {
        "document_spans_after_filter_spans": [
            span_to_payload_item(span) for span in after_filter_spans
        ],
        "document_spans_after_directives": [
            span_to_payload_item(span) for span in directive_output_spans
        ],
    }


__all__ = [
    "compute_directive_filter_metrics",
    "compute_document_filter_pipeline_counts",
    "document_span_payloads_after_stages",
    "enrich_document_directive_filter_for_export",
    "spans_after_filter_spans",
]
