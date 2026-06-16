from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from document_pipeline_core.context_pipeline.spans.pdf_text import pdf_to_text


class DocumentFixture(BaseModel):
    session_id: str
    document_id: str
    document_kind: str | None = None
    document_date: str | None = None
    source_file: str


@dataclass(frozen=True, slots=True)
class ContextCaseMeta:
    id: str
    session_id: str
    template_id: str
    doctor_note_file: str
    document_files: list[str]
    encounter_date: str | None = None
    notes: str | None = None


class DoctorNoteCase(BaseModel):
    session_id: str
    doctor_note: str


@dataclass(frozen=True, slots=True)
class ContextCase:
    meta: ContextCaseMeta
    doctor_note: DoctorNoteCase
    document_fixtures: list[DocumentFixture]


def resolve_document_source_path(
    fixture: DocumentFixture,
    *,
    cases_dir: Path,
) -> Path:
    return (cases_dir / fixture.source_file).resolve()


def load_document_text(
    fixture: DocumentFixture,
    *,
    cases_dir: Path,
) -> str:
    source_path = resolve_document_source_path(fixture, cases_dir=cases_dir)
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        return pdf_to_text(source_path)
    if suffix in {".txt", ".md"}:
        text = source_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"context_document_empty_text: {source_path}")
        return text
    raise ValueError(f"context_document_unsupported_source: {source_path}")


__all__ = [
    "ContextCase",
    "ContextCaseMeta",
    "DoctorNoteCase",
    "DocumentFixture",
    "load_document_text",
    "resolve_document_source_path",
]
