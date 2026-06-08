from __future__ import annotations

import json
import re
from typing import Any

from transcription_contract.merge import merge_consecutive_turns
from transcription_contract.models import Speaker, TranscriptionTurn

ALLOWED_SPEAKERS = {speaker.value for speaker in Speaker}


class TranscriptParseError(ValueError):
    """Raised when Gemini output cannot be parsed into structured turns."""


def parse_turns_from_response(raw: str | None) -> list[TranscriptionTurn]:
    if not raw or not raw.strip():
        raise TranscriptParseError("Empty transcription response")

    payload = _load_json_payload(raw)
    turns_raw = payload.get("turns")
    if turns_raw is None:
        raise TranscriptParseError("Missing 'turns' key in transcription response")
    if not isinstance(turns_raw, list):
        raise TranscriptParseError("'turns' must be a JSON array")

    if len(turns_raw) == 0:
        return []

    sanitized: list[TranscriptionTurn] = []
    for index, item in enumerate(turns_raw):
        if not isinstance(item, dict):
            raise TranscriptParseError(f"Turn at index {index} must be an object")
        speaker = _normalize_speaker(item.get("speaker"))
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        sanitized.append(
            TranscriptionTurn(
                speaker=speaker,
                text=text,
                overlaps_previous=bool(item.get("overlaps_previous", False)),
                overlaps_next=bool(item.get("overlaps_next", False)),
            )
        )
    return sanitized


def parse_and_sanitize_turns(raw: str | None) -> list[TranscriptionTurn]:
    return merge_consecutive_turns(parse_turns_from_response(raw))


def _load_json_payload(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise TranscriptParseError("Invalid JSON in transcription response") from exc

    if not isinstance(parsed, dict):
        raise TranscriptParseError("Transcription response must be a JSON object")
    return parsed


def _normalize_speaker(value: Any) -> str:
    if value is None:
        raise TranscriptParseError("Turn speaker is required")
    speaker = str(value).strip().upper()
    if speaker not in ALLOWED_SPEAKERS:
        raise TranscriptParseError(f"Invalid speaker: {value}")
    return speaker
