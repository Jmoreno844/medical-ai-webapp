from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from common.context_claims import (
    ClaimSourceType,
    ClinicalClaim,
    DecomposeResult,
)
from common.json_utils import extract_json_object
from common.output_detail import DEFAULT_OUTPUT_DETAIL
from common.prompts import (
    DEFAULT_PROMPT_VERSION,
)
from common.prompts import (
    load_prompt as load_prompt_from_file,
)
from common.prompts import (
    prompt_file_path as resolve_prompt_file_path,
)

from common.case_paths import CONTEXT_CASES_DIR, CONTEXT_CASES_INDEX

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = Path(__file__).resolve().parent
DEFAULT_CASES_INDEX = CONTEXT_CASES_INDEX
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "decompose"


class DoctorNoteCase(BaseModel):
    session_id: str
    doctor_note: str


@dataclass(frozen=True, slots=True)
class ContextCaseMeta:
    id: str
    session_id: str
    template_id: str
    doctor_note_file: str
    document_files: list[str]
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ContextCase:
    meta: ContextCaseMeta
    doctor_note: DoctorNoteCase
    document_fixtures: list[dict[str, object]]


def decompose_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_decompose_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return decompose_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_decompose_prompt(version)


def load_context_cases(index_path: Path) -> list[ContextCaseMeta]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("context_cases_index_must_be_object")
    cases_raw = payload.get("cases")
    if not isinstance(cases_raw, list):
        raise ValueError("context_cases_index_cases_missing")

    cases: list[ContextCaseMeta] = []
    for index, item in enumerate(cases_raw):
        if not isinstance(item, dict):
            raise ValueError(f"context_case_{index}_must_be_object")
        case_id = item.get("id")
        session_id = item.get("session_id")
        doctor_note_file = item.get("doctor_note_file")
        template_id = item.get("template_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"context_case_{index}_id_missing")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError(f"context_case_{index}_session_id_missing")
        if not isinstance(doctor_note_file, str) or not doctor_note_file.strip():
            raise ValueError(f"context_case_{index}_doctor_note_file_missing")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError(f"context_case_{index}_template_id_missing")
        document_files_raw = item.get("document_files", [])
        if not isinstance(document_files_raw, list):
            raise ValueError(f"context_case_{index}_document_files_must_be_list")
        document_files = [
            str(path).strip()
            for path in document_files_raw
            if str(path).strip()
        ]
        notes = item.get("notes")
        cases.append(
            ContextCaseMeta(
                id=case_id.strip(),
                session_id=session_id.strip(),
                template_id=template_id.strip(),
                doctor_note_file=doctor_note_file.strip(),
                document_files=document_files,
                notes=notes if isinstance(notes, str) else None,
            )
        )
    return cases


def select_context_case(
    cases: list[ContextCaseMeta],
    *,
    case_id: str,
) -> ContextCaseMeta:
    for case in cases:
        if case.id == case_id:
            return case
    raise ValueError(f"context_case_not_found: {case_id!r}")


def load_doctor_note_case(path: Path) -> DoctorNoteCase:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        return DoctorNoteCase.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"context_doctor_note_invalid: {exc}") from exc


def load_context_case(meta: ContextCaseMeta, *, cases_dir: Path) -> ContextCase:
    doctor_note_path = cases_dir / meta.doctor_note_file
    doctor_note = load_doctor_note_case(doctor_note_path)
    document_fixtures: list[dict[str, object]] = []
    for document_file in meta.document_files:
        document_path = cases_dir / document_file
        payload = json.loads(document_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"context_document_fixture_invalid: {document_file}")
        document_fixtures.append(payload)
    return ContextCase(
        meta=meta,
        doctor_note=doctor_note,
        document_fixtures=document_fixtures,
    )


def render_decompose_user_payload(case: DoctorNoteCase) -> str:
    payload = {
        "session_id": case.session_id,
        "doctor_note": case.doctor_note,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_decompose_result(raw: str) -> DecomposeResult:
    payload = extract_json_object(raw)
    try:
        result = DecomposeResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"decompose_invalid_result: {exc}") from exc
    return result


def normalize_decompose_claims(
    result: DecomposeResult,
    *,
    session_id: str,
) -> list[ClinicalClaim]:
    claims: list[ClinicalClaim] = []
    seen_ids: set[str] = set()
    for index, claim in enumerate(result.claims):
        claim_id = claim.claim_id.strip()
        if not claim_id:
            claim_id = f"{session_id}_doctor_{index}"
        if claim_id in seen_ids:
            raise ValueError(f"decompose_duplicate_claim_id: {claim_id!r}")
        seen_ids.add(claim_id)
        claims.append(
            ClinicalClaim(
                claim_id=claim_id,
                text=claim.text.strip(),
                source_type=ClaimSourceType.DOCTOR_NOTE,
                claim_type=claim.claim_type,
                source_ref=claim.source_ref,
                event_date=claim.event_date,
            )
        )
    return claims


def enrich_decompose_result_for_export(
    claims: list[ClinicalClaim],
) -> dict[str, object]:
    return {
        "claims": [claim.model_dump(mode="json") for claim in claims],
        "claim_count": len(claims),
    }


def format_decompose_debug_output(claims: list[ClinicalClaim]) -> str:
    lines = ["claims:"]
    if not claims:
        lines.append("  (none)")
        return "\n".join(lines)
    for claim in claims:
        preview = claim.text
        if len(preview) > 100:
            preview = preview[:97] + "..."
        lines.append(
            f"  - {claim.claim_id} ({claim.claim_type.value}): {preview}"
        )
    lines.append(f"\nsummary: claim_count={len(claims)}")
    return "\n".join(lines)


__all__ = [
    "CONTEXT_CASES_DIR",
    "DEFAULT_CASES_INDEX",
    "DEFAULT_OUTPUT_DETAIL",
    "DEFAULT_PROMPT_VERSION",
    "MODULE_ROOT",
    "ContextCase",
    "ContextCaseMeta",
    "DoctorNoteCase",
    "decompose_prompt_file_path",
    "enrich_decompose_result_for_export",
    "format_decompose_debug_output",
    "load_context_case",
    "load_context_cases",
    "load_decompose_prompt",
    "load_doctor_note_case",
    "load_prompt",
    "normalize_decompose_claims",
    "parse_decompose_result",
    "prompt_file_path",
    "render_decompose_user_payload",
    "select_context_case",
]
