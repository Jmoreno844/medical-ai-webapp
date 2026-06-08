from __future__ import annotations

import difflib
from dataclasses import dataclass

from transcription_contract.models import ChunkTranscript, TranscriptionTurn


@dataclass(frozen=True)
class SectionTurnsData:
    section_id: str
    section_index: int
    start_ms: int
    end_ms: int
    turns: list[TranscriptionTurn]
    status: str


def build_chunks_from_sections(
    sections: list[SectionTurnsData],
    *,
    transcribed_status: str = "transcribed",
) -> list[ChunkTranscript]:
    ordered = sorted(sections, key=lambda item: item.section_index)
    chunks: list[ChunkTranscript] = []
    for section in ordered:
        if section.status != transcribed_status:
            continue
        if not section.turns:
            continue
        chunks.append(
            ChunkTranscript(
                chunk_id=str(section.section_index),
                start_ms=section.start_ms,
                end_ms=section.end_ms,
                turns=list(section.turns),
            )
        )
    return chunks


def dedupe_adjacent_chunks(chunks: list[ChunkTranscript]) -> list[ChunkTranscript]:
    if len(chunks) <= 1:
        return [chunk.model_copy(deep=True) for chunk in chunks]

    result: list[ChunkTranscript] = [chunks[0].model_copy(deep=True)]
    for next_chunk in chunks[1:]:
        previous = result[-1]
        deduped_turns = _dedupe_turns_between_chunks(previous.turns, next_chunk.turns)
        result.append(
            ChunkTranscript(
                chunk_id=next_chunk.chunk_id,
                start_ms=next_chunk.start_ms,
                end_ms=next_chunk.end_ms,
                turns=deduped_turns,
            )
        )
    return result


def _dedupe_turns_between_chunks(
    previous_turns: list[TranscriptionTurn],
    next_turns: list[TranscriptionTurn],
) -> list[TranscriptionTurn]:
    if not previous_turns or not next_turns:
        return list(next_turns)

    previous_tail = previous_turns[-1]
    remaining = list(next_turns)
    while remaining:
        next_head = remaining[0]
        if previous_tail.speaker != next_head.speaker:
            break

        trimmed_text = _trim_duplicate_prefix(previous_tail.text, next_head.text)
        if trimmed_text is None:
            break
        if not trimmed_text:
            remaining.pop(0)
            continue

        if trimmed_text != next_head.text:
            remaining[0] = next_head.model_copy(update={"text": trimmed_text})
        break

    return remaining


def _trim_duplicate_prefix(previous_text: str, next_text: str) -> str | None:
    previous_norm = _normalize_turn_text(previous_text)
    next_norm = _normalize_turn_text(next_text)
    if not previous_norm or not next_norm:
        return None

    char_overlap = _find_char_overlap(previous_norm, next_norm)
    if char_overlap >= 5:
        return _apply_char_overlap_trim(next_text, char_overlap)

    word_overlap = _find_word_overlap(previous_norm, next_norm)
    if word_overlap >= 4:
        next_words = next_text.split()
        return " ".join(next_words[word_overlap:]).strip()

    return None


def _normalize_turn_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _find_char_overlap(previous_text: str, next_text: str) -> int:
    max_overlap = min(len(previous_text), len(next_text), 240)
    for size in range(max_overlap, 4, -1):
        if previous_text[-size:].lower() == next_text[:size].lower():
            return size
    return 0


def _apply_char_overlap_trim(next_text: str, overlap_size: int) -> str:
    lowered = next_text.lower()
    target_prefix = lowered[:overlap_size]
    index = 0
    matched = 0
    while index < len(next_text) and matched < overlap_size:
        if next_text[index].lower() == target_prefix[matched]:
            matched += 1
        index += 1
    return next_text[index:].lstrip()


def _find_word_overlap(previous_text: str, next_text: str) -> int:
    tail_words = previous_text.split()[-16:]
    head_words = next_text.split()[:16]
    matcher = difflib.SequenceMatcher(None, tail_words, head_words, autojunk=False)
    match = matcher.find_longest_match(0, len(tail_words), 0, len(head_words))
    if match.size >= 4 and match.b == 0 and match.a + match.size == len(tail_words):
        return match.size
    return 0
