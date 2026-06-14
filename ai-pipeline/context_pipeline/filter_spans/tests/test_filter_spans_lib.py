from __future__ import annotations

import json

import pytest

from common.context_spans import Directive, Span, SpanKind
from context_pipeline.filter_spans.lib import (
    filter_spans_output_schema,
    filter_spans_prompt_reference,
    load_filter_spans_prompt,
    parse_filter_spans_result,
    render_filter_spans_payload,
)


def test_parse_filter_spans_result() -> None:
    result = parse_filter_spans_result('{"drop_ids": ["s2"]}')
    assert result.drop_ids == ["s2"]


def test_audit_filter_spans_unknown_id() -> None:
    from common.context_spans import FilterSpansResult, audit_filter_spans_result

    spans = [Span(id="s1", doc="d", kind=SpanKind.LINE, text="a")]
    with pytest.raises(ValueError, match="unknown_span_id"):
        audit_filter_spans_result(spans, FilterSpansResult(drop_ids=["x"]))


def test_render_filter_spans_payload_does_not_leak_date_hint() -> None:
    spans = [
        Span(
            id="s1",
            doc="doc",
            kind=SpanKind.LINE,
            text="marzo de 2024",
            date_hint="marzo de 2024",
        )
    ]
    payload = json.loads(
        render_filter_spans_payload(
            encounter_date="2026-06-14",
            document_date="2024-03-01",
            directives=[],
            spans=spans,
            prompt_version="v002",
        )
    )
    serialized = json.dumps(payload)
    assert "date_hint" not in serialized
    assert "date_hints" not in serialized


def test_load_filter_spans_prompt_v002_returns_py_system_prompt() -> None:
    from context_pipeline.filter_spans.prompts.filter_spans_prompt_v001 import SYSTEM_PROMPT

    assert load_filter_spans_prompt("v002") == SYSTEM_PROMPT.strip()


def test_filter_spans_output_schema_v002_restricts_drop_ids() -> None:
    spans = [
        Span(id="s1", doc="doc", kind=SpanKind.LINE, text="a"),
        Span(id="s2", doc="doc", kind=SpanKind.LINE, text="b"),
    ]
    schema = filter_spans_output_schema(spans, prompt_version="v002")
    assert schema is not None
    assert schema["properties"]["drop_ids"]["items"]["enum"] == ["s1", "s2"]


def test_filter_spans_prompt_reference_v002_points_to_py_module() -> None:
    assert (
        filter_spans_prompt_reference("v002")
        == "context_pipeline/filter_spans/prompts/filter_spans_prompt_v001.py"
    )
