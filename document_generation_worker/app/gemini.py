from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from app.settings import Settings


@lru_cache(maxsize=1)
def _get_client(project_id: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


async def stream_document_generation(
    *,
    prompt: str,
    settings: Settings,
) -> AsyncIterator[str]:
    from google.genai import types

    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required")
    client = _get_client(settings.gcp_project_id, settings.vertex_ai_location)
    stream = await client.aio.models.generate_content_stream(
        model=settings.document_generation_gemini_model,
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0.4,
            top_p=0.95,
            candidate_count=1,
            max_output_tokens=settings.max_output_tokens,
        ),
    )
    async for response in stream:
        text = (getattr(response, "text", "") or "")
        if text:
            yield text
