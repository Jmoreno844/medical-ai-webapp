from __future__ import annotations

from common.context_spans import (
    Directive,
    Span,
    document_filter_directives,
    resolve_document_target,
)
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from context_pipeline.document_directive_filter.lib import (
    DocumentDirectiveFilterOutcome,
    apply_document_directives,
    apply_ignore_source_directives,
    parse_span_selector_result,
    render_span_selector_payload,
    span_selector_output_schema,
)


def run_document_directive_filter(
    *,
    spans: list[Span],
    directives: list[Directive],
    available_documents: list[str],
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v001",
) -> tuple[DocumentDirectiveFilterOutcome, list[LlmResponse]]:
    if not spans:
        return DocumentDirectiveFilterOutcome(spans=[]), []

    current_spans, _ = apply_ignore_source_directives(
        spans,
        directives,
        available_documents=available_documents,
    )
    llm_responses: list[LlmResponse] = []
    selector_results = []

    for directive in document_filter_directives(directives):
        if directive.action == "ignore_source":
            continue
        resolved_target = resolve_document_target(directive.target, available_documents)
        if resolved_target is None:
            continue
        candidate_spans = [
            span
            for span in current_spans
            if resolved_target == "__all__" or span.doc == resolved_target
        ]
        if not candidate_spans:
            continue

        user_payload = render_span_selector_payload(
            directive=directive,
            spans=candidate_spans,
            prompt_version=prompt_version,
        )
        output_schema = span_selector_output_schema(
            candidate_spans,
            prompt_version=prompt_version,
        )
        llm_response = call_llm_detailed(
            provider=model_spec.provider,
            model=model_spec.model,
            system=system_prompt,
            user=user_payload,
            output_schema=output_schema,
        )
        llm_responses.append(llm_response)
        selector_results.append(parse_span_selector_result(llm_response.content))

    outcome = apply_document_directives(
        spans,
        directives,
        available_documents=available_documents,
        selector_results=selector_results,
    )
    return outcome, llm_responses
