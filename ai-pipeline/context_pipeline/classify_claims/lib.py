from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from common.context_claims import (
    ClaimAssignment,
    ClaimClassificationSessionResult,
    ClinicalClaim,
    claim_to_payload_item,
)
from common.json_utils import extract_json_object
from common.prompts import (
    load_prompt as load_prompt_from_file,
)
from common.prompts import (
    prompt_file_path as resolve_prompt_file_path,
)
from common.templates import ClinicalTemplate

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "classify_claims"


class ClaimSectionAudit(BaseModel):
    allowed_section_ids: list[str] = Field(default_factory=list)
    assigned_section_ids: list[str] = Field(default_factory=list)
    unknown_section_ids: list[str] = Field(default_factory=list)
    duplicate_section_ids: list[str] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.unknown_section_ids and not self.duplicate_section_ids


@dataclass(frozen=True, slots=True)
class ClaimAssignmentAudit:
    expected_claim_ids: list[str]
    assigned_claim_ids: list[str]
    missing_claim_ids: list[str]
    extra_claim_ids: list[str]
    duplicate_claim_ids: list[str]
    invalid_section_claim_ids: list[str]

    @property
    def is_valid(self) -> bool:
        return (
            not self.missing_claim_ids
            and not self.extra_claim_ids
            and not self.duplicate_claim_ids
            and not self.invalid_section_claim_ids
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "expected_claim_count": len(self.expected_claim_ids),
            "assigned_claim_count": len(self.assigned_claim_ids),
            "missing_claim_ids": self.missing_claim_ids,
            "extra_claim_ids": self.extra_claim_ids,
            "duplicate_claim_ids": self.duplicate_claim_ids,
            "invalid_section_claim_ids": self.invalid_section_claim_ids,
        }


def classify_claims_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_classify_claims_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return classify_claims_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_classify_claims_prompt(version)


def render_classify_claims_payload(
    *,
    claims: list[ClinicalClaim],
    template: ClinicalTemplate,
) -> str:
    if not claims:
        raise ValueError("classify_claims_payload_requires_at_least_one_claim")
    payload = {
        "claims": [claim_to_payload_item(claim) for claim in claims],
        "template": template.to_prompt_payload(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_claim_classification_session_result(
    raw: str,
) -> ClaimClassificationSessionResult:
    payload = extract_json_object(raw)
    try:
        return ClaimClassificationSessionResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"classify_claims_invalid_result: {exc}") from exc


def audit_claim_section_ids(
    assignment: ClaimAssignment,
    template: ClinicalTemplate,
) -> ClaimSectionAudit:
    allowed_section_ids = sorted(template.section_id_set())
    allowed_set = template.section_id_set()
    assigned_section_ids = assignment.section_ids

    seen: set[str] = set()
    duplicate_section_ids: list[str] = []
    for section_id in assigned_section_ids:
        if section_id in seen and section_id not in duplicate_section_ids:
            duplicate_section_ids.append(section_id)
        seen.add(section_id)

    unknown_section_ids = sorted(
        {
            section_id
            for section_id in assigned_section_ids
            if section_id not in allowed_set
        }
    )
    return ClaimSectionAudit(
        allowed_section_ids=allowed_section_ids,
        assigned_section_ids=assigned_section_ids,
        unknown_section_ids=unknown_section_ids,
        duplicate_section_ids=duplicate_section_ids,
    )


def audit_claim_assignments(
    result: ClaimClassificationSessionResult,
    expected_claim_ids: list[str],
    template: ClinicalTemplate,
) -> ClaimAssignmentAudit:
    assigned_claim_ids = [assignment.claim_id for assignment in result.assignments]
    expected_set = set(expected_claim_ids)
    assigned_set = set(assigned_claim_ids)

    seen: set[str] = set()
    duplicate_claim_ids: list[str] = []
    for claim_id in assigned_claim_ids:
        if claim_id in seen and claim_id not in duplicate_claim_ids:
            duplicate_claim_ids.append(claim_id)
        seen.add(claim_id)

    missing_claim_ids = sorted(expected_set - assigned_set)
    extra_claim_ids = sorted(assigned_set - expected_set)

    invalid_section_claim_ids: list[str] = []
    for assignment in result.assignments:
        section_audit = audit_claim_section_ids(assignment, template)
        if not section_audit.is_valid:
            invalid_section_claim_ids.append(assignment.claim_id)

    return ClaimAssignmentAudit(
        expected_claim_ids=expected_claim_ids,
        assigned_claim_ids=assigned_claim_ids,
        missing_claim_ids=missing_claim_ids,
        extra_claim_ids=extra_claim_ids,
        duplicate_claim_ids=duplicate_claim_ids,
        invalid_section_claim_ids=invalid_section_claim_ids,
    )


def enrich_claim_classification_session_result_for_export(
    result: ClaimClassificationSessionResult,
    template: ClinicalTemplate,
    *,
    claims_by_id: dict[str, ClinicalClaim],
) -> dict[str, object]:
    headings_by_id = template.headings_by_section_id()
    assignments: list[dict[str, object]] = []
    for assignment in result.assignments:
        claim = claims_by_id.get(assignment.claim_id)
        section_headings = [
            headings_by_id.get(section_id, section_id)
            for section_id in assignment.section_ids
        ]
        entry: dict[str, object] = {
            "claim_id": assignment.claim_id,
            "section_ids": assignment.section_ids,
            "section_headings": section_headings,
        }
        if claim is not None:
            entry["claim_text"] = claim.text
            entry["source_type"] = claim.source_type.value
            entry["claim_type"] = claim.claim_type.value
        assignments.append(entry)
    return {
        "assignments": assignments,
        "assignment_count": len(assignments),
    }


def format_claim_classification_debug_output(
    result: ClaimClassificationSessionResult,
    *,
    claims_by_id: dict[str, ClinicalClaim],
    template: ClinicalTemplate,
) -> str:
    headings_by_id = template.headings_by_section_id()
    lines = ["claim assignments:"]
    for assignment in result.assignments:
        claim = claims_by_id.get(assignment.claim_id)
        preview = claim.text if claim else "(missing claim)"
        if len(preview) > 80:
            preview = preview[:77] + "..."
        section_labels = [
            f"{section_id} ({headings_by_id.get(section_id, section_id)})"
            for section_id in assignment.section_ids
        ]
        if not section_labels:
            section_labels = ["(none)"]
        lines.append(f"  - {assignment.claim_id}: {preview}")
        lines.append(f"    sections: {', '.join(section_labels)}")
    return "\n".join(lines)


def load_claim_classification_assignments(path: Path) -> list[ClaimAssignment]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    session_result = payload.get("claim_classification_session_result")
    if not isinstance(session_result, dict):
        raise ValueError("claim_classification_session_result_missing")
    assignments_raw = session_result.get("assignments")
    if not isinstance(assignments_raw, list):
        raise ValueError("claim_classification_assignments_missing")
    assignments: list[ClaimAssignment] = []
    for index, item in enumerate(assignments_raw):
        if not isinstance(item, dict):
            raise ValueError(f"claim_assignment_{index}_must_be_object")
        try:
            assignments.append(ClaimAssignment.model_validate(item))
        except ValidationError as exc:
            raise ValueError(f"claim_assignment_{index}_invalid: {exc}") from exc
    return assignments
