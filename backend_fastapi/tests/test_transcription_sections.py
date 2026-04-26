from __future__ import annotations

from app.domains.transcription.service import (
    _merge_with_light_dedup,
    _normalize_transcript_for_document,
)


def test_merge_with_light_dedup_removes_boundary_overlap() -> None:
    merged = _merge_with_light_dedup(
        "El paciente refiere dolor abdominal desde ayer.",
        "desde ayer. Niega fiebre.",
    )

    assert merged == "El paciente refiere dolor abdominal desde ayer. Niega fiebre."


def test_normalize_transcript_for_document_removes_inline_noise_tags() -> None:
    normalized = _normalize_transcript_for_document(
        "Paciente refiere dolor [tos] desde ayer.",
    )

    assert normalized == "Paciente refiere dolor desde ayer."


def test_normalize_transcript_for_document_drops_noise_only_chunk() -> None:
    normalized = _normalize_transcript_for_document("[tos]")

    assert normalized == ""


def test_normalize_transcript_for_document_preserves_inaudible() -> None:
    normalized = _normalize_transcript_for_document(
        "Paciente refiere [inaudible] intermitente.",
    )

    assert normalized == "Paciente refiere [inaudible] intermitente."
