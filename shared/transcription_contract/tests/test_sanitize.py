from __future__ import annotations

import pytest

from transcription_contract.models import TranscriptionTurn
from transcription_contract.sanitize import TranscriptParseError, parse_and_sanitize_turns


def test_parse_valid_multi_speaker_turns() -> None:
    raw = """
    {
      "turns": [
        {"speaker": "MEDICO", "text": "Buenos dias", "overlaps_previous": false, "overlaps_next": false},
        {"speaker": "PACIENTE", "text": "Hola doctor", "overlaps_previous": false, "overlaps_next": true}
      ]
    }
    """
    turns = parse_and_sanitize_turns(raw)
    assert len(turns) == 2
    assert turns[0] == TranscriptionTurn(
        speaker="MEDICO",
        text="Buenos dias",
        overlaps_previous=False,
        overlaps_next=False,
    )
    assert turns[1].speaker == "PACIENTE"
    assert turns[1].overlaps_next is True


def test_parse_empty_turns_returns_empty_list() -> None:
    assert parse_and_sanitize_turns('{"turns":[]}') == []


def test_parse_strips_text_and_drops_empty_turns() -> None:
    raw = '{"turns":[{"speaker":"MEDICO","text":"  hola  "},{"speaker":"PACIENTE","text":"   "}]}'
    turns = parse_and_sanitize_turns(raw)
    assert len(turns) == 1
    assert turns[0].text == "hola"


def test_parse_preserves_inaudible_literal() -> None:
    raw = '{"turns":[{"speaker":"PACIENTE","text":"[inaudible]"}]}'
    turns = parse_and_sanitize_turns(raw)
    assert turns[0].text == "[inaudible]"


def test_parse_rejects_invalid_speaker() -> None:
    with pytest.raises(TranscriptParseError, match="Invalid speaker"):
        parse_and_sanitize_turns('{"turns":[{"speaker":"DOCTOR","text":"hola"}]}')


def test_parse_rejects_invalid_json() -> None:
    with pytest.raises(TranscriptParseError, match="Invalid JSON"):
        parse_and_sanitize_turns("not-json")


def test_parse_rejects_missing_turns_key() -> None:
    with pytest.raises(TranscriptParseError, match="Missing 'turns'"):
        parse_and_sanitize_turns('{"segments":[]}')


def test_parse_accepts_fenced_json() -> None:
    raw = """```json
    {"turns":[{"speaker":"DESCONOCIDO","text":"hola"}]}
    ```"""
    turns = parse_and_sanitize_turns(raw)
    assert turns[0].speaker == "DESCONOCIDO"
