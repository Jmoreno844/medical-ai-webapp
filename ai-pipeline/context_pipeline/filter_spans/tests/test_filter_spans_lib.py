from __future__ import annotations

import pytest

from common.context_spans import Span, SpanKind
from context_pipeline.filter_spans.lib import parse_filter_spans_result


def test_parse_filter_spans_result() -> None:
    result = parse_filter_spans_result('{"drop_ids": ["s2"]}')
    assert result.drop_ids == ["s2"]


def test_audit_filter_spans_unknown_id() -> None:
    from common.context_spans import FilterSpansResult, audit_filter_spans_result

    spans = [Span(id="s1", doc="d", kind=SpanKind.LINE, text="a")]
    with pytest.raises(ValueError, match="unknown_span_id"):
        audit_filter_spans_result(spans, FilterSpansResult(drop_ids=["x"]))
