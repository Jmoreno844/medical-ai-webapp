from __future__ import annotations

from pydantic import BaseModel, Field


class ExternalDocumentInput(BaseModel):
    """Phase-2 ready: external clinical document supplied by the backend."""

    document_id: str
    document_kind: str = "document"
    document_date: str | None = None
    content_markdown: str | None = None
    content_pdf_gcs_uri: str | None = None


class ContextInputs(BaseModel):
    doctor_note_markdown: str | None = None
    external_documents: list[ExternalDocumentInput] = Field(default_factory=list)


def has_meaningful_doctor_note(context_inputs: ContextInputs) -> bool:
    normalized = (context_inputs.doctor_note_markdown or "").strip().lower()
    if not normalized:
        return False
    return normalized not in {"no se agregó contexto.", "no se agrego contexto."}


__all__ = [
    "ContextInputs",
    "ExternalDocumentInput",
    "has_meaningful_doctor_note",
]
