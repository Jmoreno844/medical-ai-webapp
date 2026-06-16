from __future__ import annotations

from document_pipeline_core.common.context_spans import (
    Directive,
    FilterSpansResult,
    Span,
    audit_filter_spans_result,
)
from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import ModelSpec, call_llm_detailed
from document_pipeline_core.context_pipeline.filter_spans.lib import (
    filter_spans_output_schema,
    parse_filter_spans_result,
    render_filter_spans_payload,
)


def run_filter_spans(
    *,
    encounter_date: str | None,
    document_date: str | None,
    directives: list[Directive],
    spans: list[Span],
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v001",
) -> tuple[FilterSpansResult, LlmResponse]:
    user_payload = render_filter_spans_payload(
        encounter_date=encounter_date,
        document_date=document_date,
        directives=directives,
        spans=spans,
        prompt_version=prompt_version,
    )
    output_schema = filter_spans_output_schema(spans, prompt_version=prompt_version)
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
        output_schema=output_schema,
    )
    result = parse_filter_spans_result(llm_response.content)
    audit_filter_spans_result(spans, result)
    return result, llm_response
