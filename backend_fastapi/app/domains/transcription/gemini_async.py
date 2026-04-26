from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings

SECTION_TRANSCRIPTION_PROMPT = """
Transcribe únicamente el habla realmente presente en este audio clínico.
No inventes, no completes silencios y no agregues datos clínicos.
Si una parte no es inteligible, marca [inaudible].
Devuelve solo la transcripción del segmento.
""".strip()

CONSOLIDATION_PROMPT = """
Une los segmentos en una sola transcripción clínica.
Elimina frases o palabras repetidas causadas por audio solapado.
Mejora solo puntuación y continuidad textual.
No resumas, no agregues, no omitas y no cambies hechos clínicos.
Conserva dudas o partes inaudibles como [inaudible].
Devuelve solo la transcripción consolidada.
""".strip()


@lru_cache(maxsize=1)
def _get_genai_client(project_id: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


def _vertex_location(settings: Settings) -> str:
    return (
        settings.vertex_ai_location
        or settings.cloud_tasks_region
        or "us-central1"
    )


async def transcribe_gcs_audio(
    *,
    gcs_uri: str,
    content_type: str,
    settings: Settings,
) -> str:
    from google.genai import types

    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required for Vertex AI transcription")

    client = _get_genai_client(settings.gcp_project_id, _vertex_location(settings))
    audio_part = types.Part.from_uri(file_uri=gcs_uri, mime_type=content_type)
    response = await client.aio.models.generate_content(
        model=settings.transcription_gemini_model,
        contents=[audio_part, SECTION_TRANSCRIPTION_PROMPT],
        config=types.GenerateContentConfig(
            temperature=0.0,
            top_p=0.1,
            candidate_count=1,
            max_output_tokens=2048,
        ),
    )
    transcript = (getattr(response, "text", "") or "").strip()
    if not transcript:
        raise ValueError("empty_transcription")
    return transcript


async def consolidate_transcripts(
    *,
    ordered_transcripts: list[str],
    settings: Settings,
) -> str:
    from google.genai import types

    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required for Vertex AI consolidation")

    client = _get_genai_client(settings.gcp_project_id, _vertex_location(settings))
    numbered_segments = "\n\n".join(
        f"Segmento {index + 1}:\n{text}"
        for index, text in enumerate(ordered_transcripts)
        if text.strip()
    )
    response = await client.aio.models.generate_content(
        model=settings.transcription_gemini_model,
        contents=[CONSOLIDATION_PROMPT, numbered_segments],
        config=types.GenerateContentConfig(
            temperature=0.0,
            top_p=0.1,
            candidate_count=1,
            max_output_tokens=8192,
        ),
    )
    consolidated = (getattr(response, "text", "") or "").strip()
    if not consolidated:
        raise ValueError("empty_consolidation")
    return consolidated
