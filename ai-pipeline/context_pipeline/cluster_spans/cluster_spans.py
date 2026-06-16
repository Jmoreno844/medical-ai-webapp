from __future__ import annotations

from common.context_spans import Span, SpanCluster, audit_span_clusters, span_to_payload_item
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from context_pipeline.cluster_spans.lib import (
    ClusterSpansValidationError,
    cluster_spans_output_schema,
    cluster_spans_structured_output_enabled,
    missing_span_ids_from_clusters,
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
    structured = cluster_spans_structured_output_enabled(prompt_version)
    try:
        audit_span_clusters(
            spans,
            clusters,
            require_complete_span_coverage=structured,
            require_titles=structured,
        )
    except ValueError as exc:
        missing_ids = missing_span_ids_from_clusters(spans, clusters)
        spans_by_id = {span.id: span for span in spans}
        missing_spans = [
            span_to_payload_item(spans_by_id[span_id])
            for span_id in missing_ids
            if span_id in spans_by_id
        ]
        raise ClusterSpansValidationError(
            str(exc),
            raw_response=llm_response.content,
            llm_response=llm_response,
            clusters=clusters,
            missing_span_ids=missing_ids,
            missing_spans=missing_spans,
        ) from exc
    return clusters, llm_response
