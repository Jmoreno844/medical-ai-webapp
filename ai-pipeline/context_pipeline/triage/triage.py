from __future__ import annotations

from common.context_spans import DoctorItem, TriageResult, audit_triage_result
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from context_pipeline.triage.lib import (
    parse_triage_result,
    render_triage_payload,
)


def run_triage(
    *,
    session_id: str,
    items: list[DoctorItem],
    model_spec: ModelSpec,
    system_prompt: str,
) -> tuple[TriageResult, LlmResponse]:
    user_payload = render_triage_payload(session_id=session_id, items=items)
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    result = parse_triage_result(llm_response.content)
    audit_triage_result(items, result)
    return result, llm_response
