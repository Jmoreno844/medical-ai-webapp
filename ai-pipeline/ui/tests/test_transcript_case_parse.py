from __future__ import annotations

import json

import pytest

from document_pipeline_core.common.transcripts import build_turn_catalog
from ui.discovery import parse_transcript_case_from_json


def test_parse_transcript_case_from_direct_json() -> None:
    payload = {
        "session_id": "case3",
        "language": "es",
        "chunks": [
            {
                "chunk_id": "s0",
                "turns": [
                    {"turn_id": 0, "speaker": "MEDICO", "text": "Hola"},
                    {"turn_id": 1, "speaker": "PACIENTE", "text": "Buenos días"},
                ],
            }
        ],
    }
    case = parse_transcript_case_from_json(payload)
    assert case.id == "case3"
    assert len(build_turn_catalog(case.transcript_json)) == 2


def test_parse_transcript_case_from_index_entry_shape() -> None:
    payload = {
        "id": "case1",
        "notes": "fixture",
        "transcript_json": {
            "session_id": "case1",
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [{"turn_id": 0, "speaker": "MEDICO", "text": "Hola"}],
                }
            ],
        },
    }
    case = parse_transcript_case_from_json(payload)
    assert case.id == "case1"
    assert case.notes == "fixture"


def test_parse_transcript_case_from_json_string() -> None:
    case = parse_transcript_case_from_json(
        json.dumps(
            {
                "session_id": "pasted",
                "chunks": [
                    {
                        "chunk_id": "s0",
                        "turns": [{"speaker": "PACIENTE", "text": "Me duele"}],
                    }
                ],
            }
        )
    )
    assert case.id == "pasted"


def test_parse_transcript_case_rejects_empty_chunks() -> None:
    with pytest.raises(ValueError, match="chunk"):
        parse_transcript_case_from_json({"session_id": "x", "chunks": []})
