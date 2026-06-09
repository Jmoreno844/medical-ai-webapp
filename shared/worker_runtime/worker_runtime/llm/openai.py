from __future__ import annotations

from functools import lru_cache
from typing import Any

from worker_runtime.llm.common import parse_json_object_response, require_env_value


@lru_cache(maxsize=1)
def get_openai_async_client(api_key: str):
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key)


async def create_structured_json_response(
    *,
    api_key: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    client = get_openai_async_client(require_env_value("OPENAI_API_KEY", api_key))
    response = await client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    )
    return parse_json_object_response(
        getattr(response, "output_text", "") or "",
        "openai_response_not_object",
    )
