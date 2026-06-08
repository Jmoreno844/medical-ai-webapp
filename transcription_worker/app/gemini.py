from __future__ import annotations

from functools import lru_cache

from app.audio import convert_audio_to_wav
from app.settings import Settings


SECTION_TRANSCRIPTION_PROMPT = """
Transcribe unicamente el habla realmente presente en este audio clinico.
No inventes, no completes silencios y no agregues datos clinicos.
Si una parte no es inteligible, marca [inaudible].
Devuelve solo la transcripcion del segmento.
""".strip()


def _strip_prompt_echo(transcript: str | None) -> str:
    if not transcript:
        return ""

    cleaned = transcript.replace(SECTION_TRANSCRIPTION_PROMPT, " ")
    return " ".join(cleaned.split()).strip()


@lru_cache(maxsize=1)
def _get_google_client(project_id: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


async def transcribe_audio(
    *,
    gcs_uri: str | None,
    content_type: str,
    settings: Settings,
    audio_bytes: bytes | None = None,
) -> str:
    return await _transcribe_with_google(
        gcs_uri=gcs_uri,
        content_type=content_type,
        settings=settings,
        audio_bytes=audio_bytes,
    )


async def _transcribe_with_google(
    *,
    gcs_uri: str | None,
    content_type: str,
    settings: Settings,
    audio_bytes: bytes | None = None,
) -> str:
    from google.genai import types

    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required")
    client = _get_google_client(settings.gcp_project_id, settings.vertex_ai_location)
    inline_bytes = audio_bytes
    inline_content_type = content_type
    if audio_bytes is not None and gcs_uri is None:
        inline_bytes = convert_audio_to_wav(audio_bytes)
        inline_content_type = "audio/wav"
    audio_part = (
        types.Part.from_uri(file_uri=gcs_uri, mime_type=content_type)
        if gcs_uri
        else types.Part.from_bytes(
            data=inline_bytes or b"",
            mime_type=inline_content_type,
        )
    )
    response = await client.aio.models.generate_content(
        model=settings.effective_transcription_model,
        contents=[audio_part],
        config=types.GenerateContentConfig(
            system_instruction=SECTION_TRANSCRIPTION_PROMPT,
            temperature=0.0,
            top_p=0.1,
            candidate_count=1,
            max_output_tokens=2048,
        ),
    )
    return _strip_prompt_echo(getattr(response, "text", "") or "")

