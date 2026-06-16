from __future__ import annotations

import pytest

from common.context_spans import (
    ClassifyClustersResult,
    FilterSpansResult,
    Span,
    SpanCluster,
    SpanKind,
    TriageResult,
)
from common.llm_response import LlmResponse
from common.providers import ModelSpec
from common.templates import load_template
from context_pipeline.cluster_spans.lib import ClusterSpansValidationError
from context_pipeline.config import ContextPipelineConfig, build_context_pipeline_prompt_bundle
from context_pipeline.document_directive_filter.lib import DocumentDirectiveFilterOutcome
from context_pipeline.session import (
    ContextPipelinePartialError,
    _run_context_pipeline_core,
)
from context_pipeline.span_pool import ContextSpanPools, FilteredDocumentSpans
from common.templates import DEFAULT_TEMPLATES_DIR


def _sample_spans() -> list[Span]:
    return [
        Span(id="s1", doc="doc", kind=SpanKind.LINE, text="a"),
        Span(id="s2", doc="doc", kind=SpanKind.LINE, text="b"),
    ]


def test_cluster_spans_failure_propagates_partial_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = _sample_spans()
    span_pools = ContextSpanPools(
        approved_note_spans=[],
        document_spans=spans,
    )
    filtered = FilteredDocumentSpans(
        filter_result=FilterSpansResult(drop_ids=[]),
        filtered_document_spans=spans,
        llm_response=LlmResponse(content="{}", usage={}),
    )
    directive_outcome = DocumentDirectiveFilterOutcome(spans=spans)

    def _fake_filter(**_kwargs: object) -> FilteredDocumentSpans:
        return filtered

    def _fake_directive_filter(**_kwargs: object) -> tuple[DocumentDirectiveFilterOutcome, list]:
        return directive_outcome, []

    clusters = [SpanCluster(id="c1", span_ids=["s1"], title="tema")]

    def _failing_cluster_spans(**_kwargs: object) -> tuple[list[SpanCluster], LlmResponse]:
        raise ClusterSpansValidationError(
            "context_cluster_missing_span_ids: ['s2']",
            raw_response='{"clusters":[]}',
            llm_response=LlmResponse(content='{"clusters":[]}', usage={}),
            clusters=clusters,
            missing_span_ids=["s2"],
            missing_spans=[span.model_dump(mode="json") for span in spans[1:]],
        )

    monkeypatch.setattr(
        "context_pipeline.session.filter_document_spans",
        _fake_filter,
    )
    monkeypatch.setattr(
        "context_pipeline.session.run_document_directive_filter",
        _fake_directive_filter,
    )
    monkeypatch.setattr(
        "context_pipeline.session.run_cluster_spans",
        _failing_cluster_spans,
    )

    template = load_template("minimal_outpatient_v001", templates_dir=DEFAULT_TEMPLATES_DIR)
    prompt_bundle = build_context_pipeline_prompt_bundle(ContextPipelineConfig.with_defaults())

    with pytest.raises(ContextPipelinePartialError) as exc_info:
        _run_context_pipeline_core(
            session_id="s1",
            template=template,
            template_id="minimal_outpatient_v001",
            encounter_date=None,
            document_date=None,
            doctor_items=[],
            is_pasted=False,
            triage_result=TriageResult(),
            span_pools=span_pools,
            model_spec=ModelSpec(alias="gpt", provider="openai", model="gpt"),
            prompt_bundle=prompt_bundle,
            llm_calls=[],
        )

    partial = exc_info.value
    assert partial.failed_step == "cluster_spans"
    run = partial.partial_run
    assert run.stopped_after_step == "cluster_spans"
    assert run.pipeline_error == "context_cluster_missing_span_ids: ['s2']"
    assert len(run.filtered_spans) == 2
    assert len(run.clusters) == 1
    assert run.classify_result == ClassifyClustersResult()
    assert any(call.label == "cluster_spans" for call in run.llm_calls)
    assert partial.diagnostics_payload()["missing_span_ids"] == ["s2"]
