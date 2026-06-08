from __future__ import annotations

from transcription_contract.models import TranscriptionTurn


def merge_consecutive_turns(turns: list[TranscriptionTurn]) -> list[TranscriptionTurn]:
    merged: list[TranscriptionTurn] = []

    for turn in turns:
        current = turn.model_copy(update={"text": turn.text.strip()})
        if not current.text:
            continue

        previous = merged[-1] if merged else None
        can_merge = (
            previous is not None
            and previous.speaker == current.speaker
            and previous.overlaps_next is False
            and current.overlaps_previous is False
        )

        if can_merge:
            previous.text = f"{previous.text} {current.text}".strip()
            previous.overlaps_next = current.overlaps_next
        else:
            merged.append(current)

    return merged
