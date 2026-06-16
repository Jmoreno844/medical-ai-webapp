from __future__ import annotations

from document_pipeline_core.common.context_spans import (
    AmbiguousDirective,
    Directive,
    DirectiveScope,
    Span,
    SpanKind,
)
from document_pipeline_core.context_pipeline.filter_audit import (
    document_span_payloads_after_stages,
    enrich_document_directive_filter_for_export,
)
from ui.filter_spans_audit import build_context_filter_spans_view


def _span_payload(span_id: str, *, doc: str = "case2_labs") -> dict[str, object]:
    return {
        "id": span_id,
        "doc": doc,
        "kind": "line",
        "text": f"text-{span_id}",
    }


def test_build_context_filter_spans_view_legacy_payload_without_directive_block() -> None:
    payload = {
        "document_spans": [_span_payload("1"), _span_payload("2"), _span_payload("3")],
        "filter_spans_result": {
            "drop_ids": ["2"],
            "drop_count": 1,
            "kept_span_count": 2,
        },
        "filtered_spans": [
            _span_payload("1", doc="nota_medico"),
            _span_payload("1"),
            _span_payload("3"),
        ],
    }
    view = build_context_filter_spans_view(payload)
    assert view["filter_drop_count"] == 1
    assert view["filter_kept_count"] == 2
    assert view["directive_drop_count"] == 0
    assert view["directive_kept_count"] == 2
    assert view["show_directive_no_applicable_caption"] is True
    assert [span["id"] for span in view["after_filter_spans"]] == ["1", "3"]


def test_build_context_filter_spans_view_with_directive_filter_block() -> None:
    payload = {
        "document_spans": [_span_payload("1"), _span_payload("2"), _span_payload("3")],
        "filter_spans_result": {
            "drop_ids": ["2"],
            "drop_count": 1,
            "kept_span_count": 2,
        },
        "document_spans_after_filter_spans": [_span_payload("1"), _span_payload("3")],
        "document_spans_after_directives": [_span_payload("1")],
        "document_directive_filter": {
            "input_span_count": 2,
            "kept_span_count": 1,
            "drop_count": 1,
            "drop_ids": ["3"],
            "kept_ids": ["1"],
            "ambiguous_directives": [],
            "selector_result_count": 0,
        },
        "filtered_spans": [
            _span_payload("1", doc="nota_medico"),
            _span_payload("1"),
        ],
    }
    view = build_context_filter_spans_view(payload)
    assert view["directive_drop_count"] == 1
    assert view["directive_kept_count"] == 1
    assert [span["id"] for span in view["directive_dropped_spans"]] == ["3"]
    assert view["show_directive_no_applicable_caption"] is False


def test_context_filter_spans_export_includes_directive_drop_count() -> None:
    document_spans = [
        Span(id="1", doc="case2_labs", kind=SpanKind.LINE, text="a"),
        Span(id="2", doc="case2_labs", kind=SpanKind.LINE, text="b"),
    ]
    after_filter = list(document_spans)
    after_directives = [document_spans[0]]

    stage_payloads = document_span_payloads_after_stages(
        document_spans=document_spans,
        filter_result=None,
        directive_output_spans=after_directives,
    )
    directive_export = enrich_document_directive_filter_for_export(
        input_spans=after_filter,
        output_spans=after_directives,
        ambiguous_directives=[
            AmbiguousDirective(
                directive=Directive(
                    scope=DirectiveScope.DOCUMENT,
                    action="ignore_source",
                    target="missing_doc",
                ),
                reason="unresolved_document_target",
            )
        ],
        selector_result_count=0,
    )

    assert directive_export["drop_count"] == 1
    assert directive_export["drop_ids"] == ["2"]
    assert "document_spans_after_filter_spans" in stage_payloads
    assert len(stage_payloads["document_spans_after_directives"]) == 1
