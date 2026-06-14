from __future__ import annotations

from common.context_spans import (
    Directive,
    FilterSpansResult,
    Span,
    audit_filter_spans_result,
)
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from context_pipeline.filter_spans.lib import (
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
) -> tuple[FilterSpansResult, LlmResponse]:
    user_payload = render_filter_spans_payload(
        encounter_date=encounter_date,
        document_date=document_date,
        directives=directives,
        spans=spans,
    )
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    result = parse_filter_spans_result(llm_response.content)
    audit_filter_spans_result(spans, result)
    return result, llm_response
