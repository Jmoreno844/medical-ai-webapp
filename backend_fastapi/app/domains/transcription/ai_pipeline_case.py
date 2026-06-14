from __future__ import annotations

from typing import Any

from transcription_contract.models import ChunkTranscript, ConsultationTranscript, TranscriptionTurn

_VALID_SPEAKERS = frozenset({"MEDICO", "PACIENTE", "ACOMPANANTE", "DESCONOCIDO"})


def extract_transcript_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if "chunks" in raw:
        return raw
    transcript_json = raw.get("transcript_json")
    if isinstance(transcript_json, dict) and "chunks" in transcript_json:
        return transcript_json
    raise ValueError("transcript_case_must_include_chunks")


def normalize_ai_pipeline_case_to_consultation(
    *,
    session_id: str,
    payload: dict[str, Any],
) -> ConsultationTranscript:
    transcript_payload = extract_transcript_payload(payload)
    raw_chunks = transcript_payload.get("chunks")
    if not isinstance(raw_chunks, list) or not raw_chunks:
        raise ValueError("transcript_case_chunks_must_be_non_empty_list")

    chunks: list[ChunkTranscript] = []
    cursor_ms = 0
    for index, raw_chunk in enumerate(raw_chunks):
        if not isinstance(raw_chunk, dict):
            raise ValueError(f"transcript_case_chunk_{index}_must_be_object")

        chunk_id = raw_chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            chunk_id = f"s{index}"

        start_ms = raw_chunk.get("start_ms", cursor_ms)
        end_ms = raw_chunk.get("end_ms")
        if not isinstance(start_ms, int) or start_ms < 0:
            start_ms = cursor_ms
        if not isinstance(end_ms, int) or end_ms < start_ms:
            end_ms = start_ms + 60_000
        cursor_ms = end_ms

        raw_turns = raw_chunk.get("turns")
        if not isinstance(raw_turns, list):
            raise ValueError(f"transcript_case_chunk_{index}_turns_must_be_list")

        turns: list[TranscriptionTurn] = []
        for turn_index, raw_turn in enumerate(raw_turns):
            if not isinstance(raw_turn, dict):
                raise ValueError(
                    f"transcript_case_chunk_{index}_turn_{turn_index}_must_be_object"
                )
            speaker = raw_turn.get("speaker")
            text = raw_turn.get("text")
            if not isinstance(speaker, str) or speaker not in _VALID_SPEAKERS:
                raise ValueError(
                    f"transcript_case_chunk_{index}_turn_{turn_index}_invalid_speaker"
                )
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"transcript_case_chunk_{index}_turn_{turn_index}_text_required"
                )
            turns.append(
                TranscriptionTurn(
                    speaker=speaker,
                    text=text.strip(),
                    overlaps_previous=bool(raw_turn.get("overlaps_previous", False)),
                    overlaps_next=bool(raw_turn.get("overlaps_next", False)),
                )
            )

        if turns:
            chunks.append(
                ChunkTranscript(
                    chunk_id=chunk_id.strip(),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    turns=turns,
                )
            )

    if not chunks:
        raise ValueError("transcript_case_must_include_at_least_one_turn")

    resolved_session_id = transcript_payload.get("session_id")
    if isinstance(resolved_session_id, str) and resolved_session_id.strip():
        session_id = resolved_session_id.strip()

    return ConsultationTranscript(session_id=session_id, chunks=chunks)
