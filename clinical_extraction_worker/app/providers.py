from __future__ import annotations

from typing import Any

from app.prompts import SYSTEM_PROMPT, build_extraction_prompt
from app.schema import CLINICAL_MENTIONS_SCHEMA, copy_clinical_mentions_schema
from app.settings import Settings
from worker_runtime.llm.anthropic import (
    create_structured_json_response as create_anthropic_structured_json_response,
)
from worker_runtime.llm.common import require_env_value
from worker_runtime.llm.google import (
    get_google_genai_client,
    parse_gemini_json_object_response,
)
from worker_runtime.llm.openai import create_structured_json_response


def _get_google_client(project_id: str, location: str):
    return get_google_genai_client(project_id, location)


async def extract_clinical_facts(
    *,
    work_item: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    if settings.provider_name == "gemini":
        return await _extract_with_gemini(work_item=work_item, settings=settings)
    if settings.provider_name == "openai":
        return await _extract_with_openai(work_item=work_item, settings=settings)
    if settings.provider_name == "anthropic_api":
        return await _extract_with_anthropic_api(work_item=work_item, settings=settings)
    raise ValueError(
        f"Unsupported clinical extraction provider: {settings.provider_name}"
    )


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
            response_schema=copy_clinical_mentions_schema(),
            thinking_config=types.ThinkingConfig(thinking_budget=256),
        ),
    )
    return parse_gemini_json_object_response(
        response,
        error_code="clinical_extraction_response_not_object",
        invalid_json_error_code="clinical_extraction_response_invalid_json",
    )


async def _extract_with_openai(
    *,
    work_item: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    return await create_structured_json_response(
        api_key=require_env_value("OPENAI_API_KEY", settings.openai_api_key),
        model=settings.effective_model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_extraction_prompt(work_item),
        schema_name="ClinicalMentionsV2",
        schema=copy_clinical_mentions_schema(),
    )


async def _extract_with_anthropic_api(
    *,
    work_item: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    return await create_anthropic_structured_json_response(
        api_key=settings.anthropic_api_key,
        model=settings.effective_model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_extraction_prompt(work_item),
        schema=copy_clinical_mentions_schema(),
        max_tokens=settings.clinical_extraction_max_output_tokens,
    )
