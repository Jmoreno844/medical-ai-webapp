from __future__ import annotations

from common.context_spans import Span, SpanCluster, audit_span_clusters
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from context_pipeline.cluster_spans.lib import (
    cluster_spans_output_schema,
    cluster_spans_structured_output_enabled,
    parse_cluster_spans_result,
    render_cluster_spans_payload,
)


def run_cluster_spans(
    *,
    spans: list[Span],
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v001",
) -> tuple[list[SpanCluster], LlmResponse]:
    user_payload = render_cluster_spans_payload(
        spans=spans,
        prompt_version=prompt_version,
    )
    output_schema = cluster_spans_output_schema(spans, prompt_version=prompt_version)
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
        output_schema=output_schema,
    )
    clusters = parse_cluster_spans_result(llm_response.content)
    audit_span_clusters(
        spans,
        clusters,
        require_complete_span_coverage=cluster_spans_structured_output_enabled(
            prompt_version
        ),
        require_titles=cluster_spans_structured_output_enabled(prompt_version),
    )
    return clusters, llm_response
