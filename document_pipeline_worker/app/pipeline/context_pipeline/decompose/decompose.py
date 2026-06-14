from __future__ import annotations

from common.context_claims import ClinicalClaim
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from context_pipeline.decompose.lib import (
    DoctorNoteCase,
    normalize_decompose_claims,
    parse_decompose_result,
    render_decompose_user_payload,
)


def run_decompose(
    *,
    case: DoctorNoteCase,
    model_spec: ModelSpec,
    system_prompt: str,
) -> tuple[list[ClinicalClaim], LlmResponse]:
    user_payload = render_decompose_user_payload(case)
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    result = parse_decompose_result(llm_response.content)
    claims = normalize_decompose_claims(result, session_id=case.session_id)
    return claims, llm_response
