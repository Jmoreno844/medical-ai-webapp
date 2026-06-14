from __future__ import annotations

from common.context_claims import ClinicalClaim
from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from common.templates import ClinicalTemplate
from context_pipeline.classify_claims.lib import (
    ClaimClassificationSessionResult,
    audit_claim_assignments,
    parse_claim_classification_session_result,
    render_classify_claims_payload,
)


def run_classify_claims_session(
    *,
    claims: list[ClinicalClaim],
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
) -> tuple[ClaimClassificationSessionResult, LlmResponse]:
    if not claims:
        raise ValueError("classify_claims_requires_at_least_one_claim")
    user_payload = render_classify_claims_payload(
        claims=claims,
        template=template,
    )
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    result = parse_claim_classification_session_result(llm_response.content)
    audit = audit_claim_assignments(
        result,
        [claim.claim_id for claim in claims],
        template,
    )
    if not audit.is_valid:
        if audit.missing_claim_ids:
            raise ValueError(
                f"classify_claims_missing_claim_id: {audit.missing_claim_ids[0]!r}"
            )
        if audit.extra_claim_ids:
            raise ValueError(
                f"classify_claims_extra_claim_id: {audit.extra_claim_ids[0]!r}"
            )
        if audit.duplicate_claim_ids:
            raise ValueError(
                f"classify_claims_duplicate_claim_id: {audit.duplicate_claim_ids[0]!r}"
            )
        if audit.invalid_section_claim_ids:
            raise ValueError(
                "classify_claims_invalid_section_for_claim: "
                f"{audit.invalid_section_claim_ids[0]!r}"
            )
    return result, llm_response
