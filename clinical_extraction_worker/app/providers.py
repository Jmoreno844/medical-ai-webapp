from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.prompts import SYSTEM_PROMPT, build_extraction_prompt
from app.schema import CLINICAL_FACTS_SCHEMA
from app.settings import Settings


@lru_cache(maxsize=1)
def _get_google_client(project_id: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


@lru_cache(maxsize=1)
def _get_openai_client(api_key: str):
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key)


async def extract_clinical_facts(
    *,
    work_item: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    if settings.provider_name == "gemini":
        return await _extract_with_gemini(work_item=work_item, settings=settings)
    if settings.provider_name == "openai":
        return await _extract_with_openai(work_item=work_item, settings=settings)
    raise ValueError(f"Unsupported clinical extraction provider: {settings.provider_name}")


async def _extract_with_gemini(
    *,
    work_item: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    from google.genai import types

    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required for Gemini clinical extraction")
    client = _get_google_client(settings.gcp_project_id, settings.vertex_ai_location)
    response = await client.aio.models.generate_content(
        model=settings.effective_model,
        contents=[build_extraction_prompt(work_item)],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.0,
            top_p=0.95,
            candidate_count=1,
            max_output_tokens=settings.clinical_extraction_max_output_tokens,
            response_mime_type="application/json",
            response_schema=CLINICAL_FACTS_SCHEMA,
        ),
    )
    return _parse_json_response(getattr(response, "text", "") or "")


async def _extract_with_openai(
    *,
    work_item: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI clinical extraction")
    client = _get_openai_client(api_key)
    response = await client.responses.create(
        model=settings.effective_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_extraction_prompt(work_item)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "ClinicalFactsV1",
                "schema": CLINICAL_FACTS_SCHEMA,
                "strict": True,
            }
        },
    )
    return _parse_json_response(getattr(response, "output_text", "") or "")


def _parse_json_response(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("clinical_extraction_response_not_object")
    return parsed
