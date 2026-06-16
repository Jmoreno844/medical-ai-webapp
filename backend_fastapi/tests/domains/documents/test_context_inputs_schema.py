from __future__ import annotations

from app.domains.documents.schemas import ContextInputsOut, ExternalDocumentInputOut


def test_context_inputs_out_defaults_external_documents_empty() -> None:
    payload = ContextInputsOut(doctor_note_markdown="Nota.")
    assert payload.external_documents == []


def test_external_document_input_out_optional_fields() -> None:
    payload = ExternalDocumentInputOut(document_id="lab_1")
    assert payload.document_kind == "document"
    assert payload.content_markdown is None
    assert payload.content_pdf_gcs_uri is None
