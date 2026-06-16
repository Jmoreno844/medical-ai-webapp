from __future__ import annotations


def _normalize_spans_list(spans_raw: object) -> list[dict[str, object]]:
    if not isinstance(spans_raw, list):
        return []
    return [span for span in spans_raw if isinstance(span, dict)]


def _spans_by_id(spans_raw: object) -> dict[str, dict[str, object]]:
    return {
        str(span.get("id")): span
        for span in _normalize_spans_list(spans_raw)
        if span.get("id") is not None
    }


def _spans_for_ids(
    span_ids: object,
    spans_by_id: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    if not isinstance(span_ids, list):
        return []
    spans: list[dict[str, object]] = []
    for span_id in span_ids:
        span = spans_by_id.get(str(span_id))
        if span is not None:
            spans.append(span)
    return spans


def _filter_spans_metrics(payload: dict[str, object]) -> dict[str, int]:
    filter_result = payload.get("filter_spans_result")
    document_spans = _normalize_spans_list(payload.get("document_spans"))
    if isinstance(filter_result, dict):
        drop_count = filter_result.get("drop_count")
        kept_count = filter_result.get("kept_span_count")
        if isinstance(drop_count, int) and isinstance(kept_count, int):
            return {
                "drop_count": drop_count,
                "kept_count": kept_count,
            }
    return {
        "drop_count": 0,
        "kept_count": len(document_spans),
    }


def _directive_filter_metrics(payload: dict[str, object]) -> dict[str, int]:
    directive_block = payload.get("document_directive_filter")
    if not isinstance(directive_block, dict):
        after_filter = _normalize_spans_list(
            payload.get("document_spans_after_filter_spans")
        )
        return {
            "input_count": len(after_filter),
            "drop_count": 0,
            "kept_count": len(after_filter),
        }

    input_count = directive_block.get("input_span_count")
    drop_count = directive_block.get("drop_count")
    kept_count = directive_block.get("kept_span_count")
    return {
        "input_count": int(input_count) if isinstance(input_count, int) else 0,
        "drop_count": int(drop_count) if isinstance(drop_count, int) else 0,
        "kept_count": int(kept_count) if isinstance(kept_count, int) else 0,
    }


def build_context_filter_spans_view(payload: dict[str, object]) -> dict[str, object]:
    document_spans = _normalize_spans_list(payload.get("document_spans"))
    approved_note_spans = _normalize_spans_list(payload.get("approved_note_spans"))
    merged_spans = _normalize_spans_list(payload.get("filtered_spans"))

    filter_metrics = _filter_spans_metrics(payload)
    directive_metrics = _directive_filter_metrics(payload)

    after_filter_spans = _normalize_spans_list(
        payload.get("document_spans_after_filter_spans")
    )
    if not after_filter_spans:
        filter_result = payload.get("filter_spans_result")
        drop_ids: list[str] = []
        if isinstance(filter_result, dict) and isinstance(
            filter_result.get("drop_ids"), list
        ):
            drop_ids = [str(span_id) for span_id in filter_result["drop_ids"]]
        drop_set = set(drop_ids)
        after_filter_spans = [
            span
            for span in document_spans
            if str(span.get("id", "")) and str(span.get("id")) not in drop_set
        ]

    after_directive_spans = _normalize_spans_list(
        payload.get("document_spans_after_directives")
    )
    if not after_directive_spans:
        directive_block = payload.get("document_directive_filter")
        if isinstance(directive_block, dict) and isinstance(
            directive_block.get("kept_ids"), list
        ):
            after_directive_spans = _spans_for_ids(
                directive_block["kept_ids"],
                _spans_by_id(after_filter_spans),
            )
        else:
            after_directive_spans = list(after_filter_spans)

    filter_drop_ids: list[str] = []
    filter_result = payload.get("filter_spans_result")
    if isinstance(filter_result, dict) and isinstance(filter_result.get("drop_ids"), list):
        filter_drop_ids = [str(span_id) for span_id in filter_result["drop_ids"]]

    directive_drop_ids: list[str] = []
    directive_block = payload.get("document_directive_filter")
    if isinstance(directive_block, dict) and isinstance(
        directive_block.get("drop_ids"), list
    ):
        directive_drop_ids = [str(span_id) for span_id in directive_block["drop_ids"]]
    elif after_filter_spans and after_directive_spans:
        kept_set = {str(span.get("id")) for span in after_directive_spans if span.get("id")}
        directive_drop_ids = [
            str(span.get("id"))
            for span in after_filter_spans
            if span.get("id") and str(span.get("id")) not in kept_set
        ]

    after_filter_by_id = _spans_by_id(after_filter_spans)
    filter_dropped_spans = _spans_for_ids(filter_drop_ids, _spans_by_id(document_spans))
    directive_dropped_spans = _spans_for_ids(directive_drop_ids, after_filter_by_id)

    directive_block = payload.get("document_directive_filter")
    if isinstance(directive_block, dict):
        directive_drop_count = directive_metrics["drop_count"]
        directive_kept_count = directive_metrics["kept_count"]
    else:
        directive_drop_count = len(directive_dropped_spans)
        directive_kept_count = len(after_directive_spans)

    return {
        "filter_drop_count": filter_metrics["drop_count"],
        "filter_kept_count": filter_metrics["kept_count"],
        "directive_drop_count": directive_drop_count,
        "directive_kept_count": directive_kept_count,
        "show_directive_no_applicable_caption": directive_drop_count == 0,
        "approved_note_spans": approved_note_spans,
        "document_input_spans": document_spans,
        "filter_dropped_spans": filter_dropped_spans,
        "after_filter_spans": after_filter_spans,
        "directive_dropped_spans": directive_dropped_spans,
        "after_directive_spans": after_directive_spans,
        "merged_spans": merged_spans,
    }


__all__ = ["build_context_filter_spans_view"]
