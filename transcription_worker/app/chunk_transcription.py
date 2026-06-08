from __future__ import annotations

from app.gemini import transcribe_audio, transcribe_audio_raw_turns
from app.settings import Settings
from transcription_contract.models import TranscriptionTurn


async def transcribe_chunk_audio(
    *,
    gcs_uri: str | None,
    content_type: str,
    audio_bytes: bytes | None,
    settings: Settings,
) -> list[TranscriptionTurn]:
    return await transcribe_audio(
        gcs_uri=gcs_uri,
        content_type=content_type,
        settings=settings,
        audio_bytes=audio_bytes,
    )


async def transcribe_chunk_audio_raw(
    *,
    gcs_uri: str | None,
    content_type: str,
    audio_bytes: bytes | None,
    settings: Settings,
) -> list[TranscriptionTurn]:
    return await transcribe_audio_raw_turns(
        gcs_uri=gcs_uri,
        content_type=content_type,
        settings=settings,
        audio_bytes=audio_bytes,
    )
