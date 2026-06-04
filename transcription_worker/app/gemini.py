from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from app.audio import convert_audio_to_openai_wav, convert_audio_to_wav
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


@lru_cache(maxsize=1)
def _get_openai_client(api_key: str):
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key)


async def transcribe_audio(
    *,
    gcs_uri: str | None,
    content_type: str,
    settings: Settings,
    audio_bytes: bytes | None = None,
) -> str:
    provider = settings.transcription_provider_name
    if provider in {"google", "google_genai", "gemini"}:
        return await _transcribe_with_google(
            gcs_uri=gcs_uri,
            content_type=content_type,
            settings=settings,
            audio_bytes=audio_bytes,
        )
    if provider in {"openai", "openai_api"}:
        if audio_bytes is None:
            raise ValueError("audio_bytes are required for OpenAI transcription")
        return await _transcribe_with_openai(
            audio_bytes=audio_bytes,
            content_type=content_type,
            settings=settings,
        )
    raise ValueError(f"Unsupported transcription provider: {provider}")


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


async def _transcribe_with_openai(
    *,
    audio_bytes: bytes,
    content_type: str,
    settings: Settings,
) -> str:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI transcription")

    client = _get_openai_client(api_key)
    transcoded_audio = convert_audio_to_openai_wav(audio_bytes)
    audio_file = BytesIO(transcoded_audio)
    audio_file.name = "section.wav"
    response = await client.audio.transcriptions.create(
        model=settings.effective_transcription_model,
        file=audio_file,
        prompt=SECTION_TRANSCRIPTION_PROMPT,
        response_format="text",
    )
    return _strip_prompt_echo(str(response))


def _filename_for_content_type(content_type: str) -> str:
    normalized = _normalize_content_type(content_type)
    if normalized == "audio/webm":
        return "section.webm"
    if normalized == "audio/wav":
        return "section.wav"
    if normalized in {"audio/mpeg", "audio/mp3", "audio/mpga"}:
        return "section.mp3"
    if normalized in {"audio/mp4", "audio/m4a", "audio/x-m4a"}:
        return "section.m4a"
    if normalized in {"audio/ogg", "audio/opus"}:
        return "section.ogg"
    return "section.audio"


def _normalize_content_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()
