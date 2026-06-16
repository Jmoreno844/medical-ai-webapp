from __future__ import annotations

from app.pipeline.orchestrator import parse_context_inputs


def test_parse_context_inputs_structured_payload() -> None:
    parsed = parse_context_inputs(
        {
            "context_inputs": {
                "doctor_note_markdown": "Nota del médico.",
                "external_documents": [],
            }
        }
    )
    assert parsed.doctor_note_markdown == "Nota del médico."
    assert parsed.external_documents == []


def test_parse_context_inputs_legacy_fallback() -> None:
    parsed = parse_context_inputs({"context_content": "Contexto legado."})
    assert parsed.doctor_note_markdown == "Contexto legado."
    assert parsed.external_documents == []
