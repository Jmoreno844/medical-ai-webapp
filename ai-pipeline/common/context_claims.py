from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ClaimSourceType(StrEnum):
    DOCTOR_NOTE = "doctor_note"
    PATIENT_DOCUMENT = "patient_document"


class ClaimType(StrEnum):
    OBSERVATION = "observation"
    MEASUREMENT = "measurement"
    PRIOR_FACT = "prior_fact"
    HYPOTHESIS = "hypothesis"
    ROUTING_HINT = "routing_hint"
    CORRECTION = "correction"


class ClaimSourceRef(BaseModel):
    document_id: str | None = None
    page: int | None = None
    chunk_index: int | None = None


class ClinicalClaim(BaseModel):
    claim_id: str
    text: str
    source_type: ClaimSourceType
    claim_type: ClaimType
    source_ref: ClaimSourceRef | None = None
    event_date: str | None = None
    document_kind: str | None = None


class DecomposeClaimDraft(BaseModel):
    claim_id: str
    text: str
    claim_type: ClaimType
    event_date: str | None = None


class DecomposeResult(BaseModel):
    claims: list[DecomposeClaimDraft] = Field(default_factory=list)


class ExtractClaimDraft(BaseModel):
    claim_id: str
    text: str
    claim_type: ClaimType
    event_date: str | None = None
    source_ref: ClaimSourceRef | None = None


class ExtractResult(BaseModel):
    document_id: str
    document_kind: str
    document_summary: str = ""
    claims: list[ExtractClaimDraft] = Field(default_factory=list)


class ClaimAssignment(BaseModel):
    claim_id: str
    section_ids: list[str] = Field(default_factory=list)


class ClaimClassificationSessionResult(BaseModel):
    assignments: list[ClaimAssignment] = Field(default_factory=list)


def claim_to_payload_item(claim: ClinicalClaim) -> dict[str, object]:
    payload: dict[str, object] = {
        "claim_id": claim.claim_id,
        "text": claim.text,
        "source_type": claim.source_type.value,
        "claim_type": claim.claim_type.value,
    }
    if claim.source_ref is not None:
        payload["source_ref"] = claim.source_ref.model_dump(exclude_none=True)
    if claim.event_date:
        payload["event_date"] = claim.event_date
    if claim.document_kind:
        payload["document_kind"] = claim.document_kind
    return payload


def merge_claim_lists(*claim_lists: list[ClinicalClaim]) -> list[ClinicalClaim]:
    merged: list[ClinicalClaim] = []
    seen_ids: set[str] = set()
    for claims in claim_lists:
        for claim in claims:
            if claim.claim_id in seen_ids:
                raise ValueError(f"context_duplicate_claim_id: {claim.claim_id!r}")
            seen_ids.add(claim.claim_id)
            merged.append(claim)
    return merged


def group_claims_by_section(
    assignments: list[ClaimAssignment],
    claims_by_id: dict[str, ClinicalClaim],
    allowed_section_ids: set[str],
) -> dict[str, list[ClinicalClaim]]:
    grouped: dict[str, list[ClinicalClaim]] = {
        section_id: [] for section_id in allowed_section_ids
    }
    seen_per_section: dict[str, set[str]] = {
        section_id: set() for section_id in allowed_section_ids
    }

    for assignment in assignments:
        if assignment.claim_id not in claims_by_id:
            raise ValueError(
                f"context_claim_not_found: {assignment.claim_id!r}"
            )
        claim = claims_by_id[assignment.claim_id]
        for section_id in assignment.section_ids:
            if section_id not in allowed_section_ids:
                raise ValueError(f"context_unknown_section_id: {section_id!r}")
            if assignment.claim_id in seen_per_section[section_id]:
                continue
            grouped[section_id].append(claim)
            seen_per_section[section_id].add(assignment.claim_id)
    return grouped


DocumentKind = Literal[
    "laboratorio",
    "epicrisis",
    "imagen",
    "formula",
    "otro",
]

__all__ = [
    "ClaimAssignment",
    "ClaimClassificationSessionResult",
    "ClaimSourceRef",
    "ClaimSourceType",
    "ClaimType",
    "ClinicalClaim",
    "DecomposeClaimDraft",
    "DecomposeResult",
    "DocumentKind",
    "ExtractClaimDraft",
    "ExtractResult",
    "claim_to_payload_item",
    "group_claims_by_section",
    "merge_claim_lists",
]
