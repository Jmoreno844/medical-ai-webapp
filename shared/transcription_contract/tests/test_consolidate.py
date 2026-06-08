from __future__ import annotations

from transcription_contract.consolidate import (
    SectionTurnsData,
    build_chunks_from_sections,
    dedupe_adjacent_chunks,
)
from transcription_contract.models import ChunkTranscript, TranscriptionTurn


def _turn(speaker: str, text: str) -> TranscriptionTurn:
    return TranscriptionTurn(speaker=speaker, text=text)


def test_build_chunks_orders_by_section_index() -> None:
    sections = [
        SectionTurnsData("s2", 2, 2000, 3000, [_turn("PACIENTE", "dos")], "transcribed"),
        SectionTurnsData("s1", 1, 0, 1000, [_turn("MEDICO", "uno")], "transcribed"),
    ]
    chunks = build_chunks_from_sections(sections)
    assert [chunk.chunk_id for chunk in chunks] == ["1", "2"]


def test_build_chunks_skips_non_transcribed_and_empty() -> None:
    sections = [
        SectionTurnsData("s1", 1, 0, 1000, [], "transcribed"),
        SectionTurnsData("s2", 2, 1000, 2000, [_turn("MEDICO", "hola")], "discarded_no_speech"),
        SectionTurnsData("s3", 3, 2000, 3000, [_turn("PACIENTE", "si")], "transcribed"),
    ]
    chunks = build_chunks_from_sections(sections)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "3"


def test_dedupe_removes_duplicate_prefix_between_adjacent_chunks() -> None:
    chunks = [
        ChunkTranscript(
            chunk_id="1",
            start_ms=0,
            end_ms=1000,
            turns=[_turn("MEDICO", "Buenos dias como estas")],
        ),
        ChunkTranscript(
            chunk_id="2",
            start_ms=900,
            end_ms=2000,
            turns=[_turn("MEDICO", "como estas hoy")],
        ),
    ]
    deduped = dedupe_adjacent_chunks(chunks)
    assert deduped[0].turns[0].text == "Buenos dias como estas"
    assert deduped[1].turns[0].text == "hoy"


def test_dedupe_does_not_merge_different_speakers() -> None:
    chunks = [
        ChunkTranscript(
            chunk_id="1",
            start_ms=0,
            end_ms=1000,
            turns=[_turn("MEDICO", "Buenos dias")],
        ),
        ChunkTranscript(
            chunk_id="2",
            start_ms=900,
            end_ms=2000,
            turns=[_turn("PACIENTE", "Buenos dias doctor")],
        ),
    ]
    deduped = dedupe_adjacent_chunks(chunks)
    assert deduped[1].turns[0].text == "Buenos dias doctor"


def test_dedupe_removes_fully_duplicate_first_turn() -> None:
    chunks = [
        ChunkTranscript(
            chunk_id="1",
            start_ms=0,
            end_ms=1000,
            turns=[_turn("PACIENTE", "me duele la cabeza")],
        ),
        ChunkTranscript(
            chunk_id="2",
            start_ms=900,
            end_ms=2000,
            turns=[
                _turn("PACIENTE", "me duele la cabeza"),
                _turn("MEDICO", "desde cuando"),
            ],
        ),
    ]
    deduped = dedupe_adjacent_chunks(chunks)
    assert len(deduped[1].turns) == 1
    assert deduped[1].turns[0].speaker == "MEDICO"
