from __future__ import annotations

from common.context_spans import Span, SpanCluster, audit_span_clusters
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from context_pipeline.cluster_spans.lib import (
    parse_cluster_spans_result,
    render_cluster_spans_payload,
)


def run_cluster_spans(
    *,
    spans: list[Span],
    model_spec: ModelSpec,
    system_prompt: str,
) -> tuple[list[SpanCluster], LlmResponse]:
    user_payload = render_cluster_spans_payload(spans=spans)
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    clusters = parse_cluster_spans_result(llm_response.content)
    audit_span_clusters(spans, clusters)
    return clusters, llm_response
