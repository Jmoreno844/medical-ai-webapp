from __future__ import annotations

from common.context_spans import ClassifyClustersResult, Span, SpanCluster
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from common.templates import ClinicalTemplate
from context_pipeline.classify_clusters.lib import (
    audit_classify_clusters,
    classify_clusters_output_schema,
    classify_clusters_uses_py_prompt,
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
    encounter_date: str | None = None,
    document_date: str | None = None,
    prompt_version: str = "v001",
) -> tuple[ClassifyClustersResult, LlmResponse]:
    user_payload = render_classify_clusters_payload(
        template=template,
        clusters=clusters,
        spans=spans,
        encounter_date=encounter_date,
        document_date=document_date,
        prompt_version=prompt_version,
    )
    output_schema = classify_clusters_output_schema(
        template=template,
        clusters=clusters,
        prompt_version=prompt_version,
    )
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
        output_schema=output_schema,
    )
    result = parse_classify_clusters_result(llm_response.content)
    audit_classify_clusters(
        clusters,
        template,
        result,
        require_complete_cluster_coverage=classify_clusters_uses_py_prompt(
            prompt_version
        ),
    )
    return result, llm_response
