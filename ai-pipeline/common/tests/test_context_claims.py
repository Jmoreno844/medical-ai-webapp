from __future__ import annotations

import pytest

from common.context_claims import (
    ClaimAssignment,
    ClaimSourceType,
    ClaimType,
    ClinicalClaim,
    group_claims_by_section,
    merge_claim_lists,
)


def _claim(claim_id: str) -> ClinicalClaim:
    return ClinicalClaim(
        claim_id=claim_id,
        text=f"text {claim_id}",
        source_type=ClaimSourceType.DOCTOR_NOTE,
        claim_type=ClaimType.OBSERVATION,
    )


def test_merge_claim_lists_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="context_duplicate_claim_id"):
        merge_claim_lists([_claim("c1")], [_claim("c1")])


def test_group_claims_by_section_supports_multi_section_claim() -> None:
    claims = [_claim("c1"), _claim("c2")]
    claims_by_id = {claim.claim_id: claim for claim in claims}
    assignments = [
        ClaimAssignment(claim_id="c1", section_ids=["antecedentes", "examen_fisico"]),
        ClaimAssignment(claim_id="c2", section_ids=["antecedentes"]),
    ]
    allowed = {"antecedentes", "examen_fisico", "motivo_consulta"}
    grouped = group_claims_by_section(assignments, claims_by_id, allowed)
    assert [item.claim_id for item in grouped["antecedentes"]] == ["c1", "c2"]
    assert [item.claim_id for item in grouped["examen_fisico"]] == ["c1"]
    assert grouped["motivo_consulta"] == []


def test_group_claims_by_section_rejects_unknown_section() -> None:
    claims_by_id = {"c1": _claim("c1")}
    assignments = [ClaimAssignment(claim_id="c1", section_ids=["unknown"])]
    with pytest.raises(ValueError, match="context_unknown_section_id"):
        group_claims_by_section(assignments, claims_by_id, {"antecedentes"})
