from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

from anthropic import transform_schema

from worker_runtime.llm.common import parse_json_object_response, require_env_value


@lru_cache(maxsize=1)
def get_anthropic_vertex_client(project_id: str, region: str):
    from anthropic import AnthropicVertex

    return AnthropicVertex(project_id=project_id, region=region)


@lru_cache(maxsize=1)
def get_anthropic_api_client(api_key: str):
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=api_key)


def require_anthropic_api_key(api_key: str | None) -> str:
    return require_env_value("ANTHROPIC_API_KEY", api_key)


def _extract_message_text(content: object) -> str:
    if not isinstance(content, list):
        return ""
    for block in content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            if text:
                return text
    return ""


async def create_structured_json_response(
    *,
    api_key: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    client = get_anthropic_api_client(require_anthropic_api_key(api_key))
    api_schema = transform_schema(deepcopy(schema))
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": api_schema,
            }
        },
    )
    parsed_output = getattr(response, "parsed_output", None)
    if isinstance(parsed_output, dict):
        return parsed_output
    return parse_json_object_response(
        _extract_message_text(getattr(response, "content", None)),
        "anthropic_response_not_object",
    )
