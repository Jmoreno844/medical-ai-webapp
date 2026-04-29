from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.domains.transcription.service import (
    _merge_session_with_existing_document,
    _merge_with_light_dedup,
    _normalize_transcript_for_document,
    is_recording_session_ready_for_consolidation,
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


def test_merge_session_with_existing_document_appends_resumed_transcript() -> None:
    recording_session = SimpleNamespace(
        consolidated_transcript="Paciente refiere cefalea desde ayer.",
    )

    merged = _merge_session_with_existing_document(
        recording_session,
        "Niega fiebre.",
    )

    assert merged == "Paciente refiere cefalea desde ayer.\n\nNiega fiebre."


def test_recording_session_ready_for_consolidation_requires_finish_and_sections() -> None:
    ready_session = SimpleNamespace(
        finished_at=datetime.now(timezone.utc),
        sections=[
            SimpleNamespace(status="transcribed"),
            SimpleNamespace(status="transcribed"),
        ],
    )
    pending_session = SimpleNamespace(
        finished_at=datetime.now(timezone.utc),
        sections=[SimpleNamespace(status="registered")],
    )
    recording_session = SimpleNamespace(
        finished_at=None,
        sections=[SimpleNamespace(status="transcribed")],
    )

    assert is_recording_session_ready_for_consolidation(ready_session) is True
    assert is_recording_session_ready_for_consolidation(pending_session) is False
    assert is_recording_session_ready_for_consolidation(recording_session) is False
