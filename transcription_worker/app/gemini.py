from __future__ import annotations

from functools import lru_cache

from app.settings import Settings


SECTION_TRANSCRIPTION_PROMPT = """
Transcribe únicamente el habla realmente presente en este audio clínico.
No inventes, no completes silencios y no agregues datos clínicos.
Si una parte no es inteligible, marca [inaudible].
Devuelve solo la transcripción del segmento.
""".strip()


@lru_cache(maxsize=1)
def _get_client(project_id: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


async def transcribe_gcs_audio(
    *,
    gcs_uri: str,
    content_type: str,
    settings: Settings,
) -> str:
    from google.genai import types

    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required")
    client = _get_client(settings.gcp_project_id, settings.vertex_ai_location)
    response = await client.aio.models.generate_content(
        model=settings.transcription_gemini_model,
        contents=[
            types.Part.from_uri(file_uri=gcs_uri, mime_type=content_type),
            SECTION_TRANSCRIPTION_PROMPT,
        ],
        config=types.GenerateContentConfig(
            temperature=0.0,
            top_p=0.1,
            candidate_count=1,
            max_output_tokens=2048,
        ),
    )
    return (getattr(response, "text", "") or "").strip()
