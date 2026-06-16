from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from document_pipeline_core.context_pipeline.fixtures import (
    ContextCase,
    ContextCaseMeta,
    DoctorNoteCase,
    DocumentFixture,
    load_document_text,
    resolve_document_source_path,
)

from harness.paths import CONTEXT_CASES_DIR, CONTEXT_CASES_INDEX

DEFAULT_CASES_INDEX = CONTEXT_CASES_INDEX


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
        encounter_date = item.get("encounter_date")
        notes = item.get("notes")
        cases.append(
            ContextCaseMeta(
                id=case_id.strip(),
                session_id=session_id.strip(),
                template_id=template_id.strip(),
                doctor_note_file=doctor_note_file.strip(),
                document_files=document_files,
                encounter_date=(
                    encounter_date.strip()
                    if isinstance(encounter_date, str) and encounter_date.strip()
                    else None
                ),
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


def load_document_fixture(path: Path) -> DocumentFixture:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        return DocumentFixture.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"context_document_fixture_invalid: {exc}") from exc


def load_context_case(meta: ContextCaseMeta, *, cases_dir: Path) -> ContextCase:
    doctor_note_path = cases_dir / meta.doctor_note_file
    doctor_note = load_doctor_note_case(doctor_note_path)
    document_fixtures: list[DocumentFixture] = []
    for document_file in meta.document_files:
        document_path = cases_dir / document_file
        document_fixtures.append(load_document_fixture(document_path))
    return ContextCase(
        meta=meta,
        doctor_note=doctor_note,
        document_fixtures=document_fixtures,
    )


__all__ = [
    "CONTEXT_CASES_DIR",
    "DEFAULT_CASES_INDEX",
    "ContextCase",
    "ContextCaseMeta",
    "DoctorNoteCase",
    "DocumentFixture",
    "load_context_case",
    "load_context_cases",
    "load_document_fixture",
    "load_document_text",
    "load_doctor_note_case",
    "resolve_document_source_path",
    "select_context_case",
]
