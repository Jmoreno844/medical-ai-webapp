from __future__ import annotations

import pytest

from app.domains.transcription.ai_pipeline_case import (
    extract_transcript_payload,
    normalize_ai_pipeline_case_to_consultation,
)


def test_extract_transcript_payload_from_case_file_shape() -> None:
    payload = {
        "session_id": "case1",
        "chunks": [{"chunk_id": "s0", "turns": []}],
    }
    assert extract_transcript_payload(payload) is payload


def test_extract_transcript_payload_from_index_entry_shape() -> None:
    payload = {
        "id": "case1",
        "transcript_json": {
            "session_id": "case1",
            "chunks": [{"chunk_id": "s0", "turns": []}],
        },
    }
    extracted = extract_transcript_payload(payload)
    assert extracted["session_id"] == "case1"


def test_normalize_ai_pipeline_case_assigns_turn_timings() -> None:
    consultation = normalize_ai_pipeline_case_to_consultation(
        session_id="fallback",
        payload={
            "session_id": "case3",
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "turn_id": 0,
                            "speaker": "MEDICO",
                            "text": "Hola",
                        },
                        {
                            "turn_id": 1,
                            "speaker": "PACIENTE",
                            "text": "Buenos días",
                        },
                    ],
                }
            ],
        },
    )
    assert consultation.session_id == "case3"
    assert len(consultation.chunks) == 1
    assert consultation.chunks[0].start_ms == 0
    assert consultation.chunks[0].end_ms == 60_000
    assert consultation.chunks[0].turns[0].speaker == "MEDICO"
    assert consultation.chunks[0].turns[0].text == "Hola"


def test_normalize_ai_pipeline_case_rejects_empty_turns() -> None:
    with pytest.raises(ValueError, match="at_least_one_turn"):
        normalize_ai_pipeline_case_to_consultation(
            session_id="case1",
            payload={"chunks": [{"chunk_id": "s0", "turns": []}]},
        )
