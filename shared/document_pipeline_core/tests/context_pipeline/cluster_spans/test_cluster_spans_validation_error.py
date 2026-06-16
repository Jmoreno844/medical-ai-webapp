from __future__ import annotations

import pytest

from document_pipeline_core.common.context_spans import Span, SpanKind, SpanCluster
from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import ModelSpec
from document_pipeline_core.context_pipeline.cluster_spans.cluster_spans import run_cluster_spans
from document_pipeline_core.context_pipeline.cluster_spans.lib import (
    ClusterSpansValidationError,
    missing_span_ids_from_clusters,
)


def test_missing_span_ids_from_clusters() -> None:
    spans = [
        Span(id="s1", doc="doc", kind=SpanKind.LINE, text="a"),
        Span(id="s2", doc="doc", kind=SpanKind.LINE, text="b"),
    ]
    clusters = [SpanCluster(id="c1", span_ids=["s1"], title="tema")]
    assert missing_span_ids_from_clusters(spans, clusters) == ["s2"]


def test_cluster_spans_validation_error_diagnostics() -> None:
    clusters = [SpanCluster(id="c1", span_ids=["s1"], title="tema")]
    exc = ClusterSpansValidationError(
        "context_cluster_missing_span_ids: ['s2']",
        raw_response='{"clusters":[]}',
        clusters=clusters,
        missing_span_ids=["s2"],
        missing_spans=[{"id": "s2", "doc": "doc", "kind": "line", "text": "b"}],
    )
    diagnostics = exc.diagnostics()
    assert diagnostics["raw_response"] == '{"clusters":[]}'
    assert diagnostics["missing_span_ids"] == ["s2"]
    assert diagnostics["missing_spans"][0]["id"] == "s2"
    assert diagnostics["cluster_spans_result"]["cluster_count"] == 1


def test_run_cluster_spans_missing_coverage_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = [
        Span(id="s1", doc="doc", kind=SpanKind.LINE, text="a"),
        Span(id="s2", doc="doc", kind=SpanKind.LINE, text="b"),
    ]

    def _fake_llm(**_kwargs: object) -> LlmResponse:
        return LlmResponse(
            content=(
                '{"clusters": [{"id": "c1", "span_ids": ["s1"], "title": "tema"}]}'
            ),
            usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr(
        "document_pipeline_core.context_pipeline.cluster_spans.cluster_spans.call_llm_detailed",
        _fake_llm,
    )

    with pytest.raises(ClusterSpansValidationError) as exc_info:
        run_cluster_spans(
            spans=spans,
            model_spec=ModelSpec(alias="gpt", provider="openai", model="gpt"),
            system_prompt="cluster",
            prompt_version="v002",
        )

    exc = exc_info.value
    assert exc.missing_span_ids == ["s2"]
    assert len(exc.clusters) == 1
    assert exc.raw_response is not None
    assert exc.llm_response is not None
    assert exc.missing_spans[0]["text"] == "b"
