from __future__ import annotations

from common.context_spans import ClassifyClustersResult, Span, SpanCluster
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from common.templates import ClinicalTemplate
from context_pipeline.classify_clusters.lib import (
    audit_classify_clusters,
    parse_classify_clusters_result,
    render_classify_clusters_payload,
)


def run_classify_clusters(
    *,
    template: ClinicalTemplate,
    clusters: list[SpanCluster],
    spans: list[Span],
    model_spec: ModelSpec,
    system_prompt: str,
) -> tuple[ClassifyClustersResult, LlmResponse]:
    user_payload = render_classify_clusters_payload(
        template=template,
        clusters=clusters,
        spans=spans,
    )
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    result = parse_classify_clusters_result(llm_response.content)
    audit_classify_clusters(clusters, template, result)
    return result, llm_response
