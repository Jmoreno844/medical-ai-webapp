from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from worker_runtime.llm.common import parse_json_object_response


@lru_cache(maxsize=1)
def get_google_genai_client(project_id: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


def stringify_finish_reason(value: object) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return str(value)


def parse_gemini_json_object_response(
    response: object,
    *,
    error_code: str,
    invalid_json_error_code: str = "gemini_response_invalid_json",
) -> dict[str, Any]:
    candidates = getattr(response, "candidates", None) or []
    candidate = candidates[0] if candidates else None
    finish_reason = stringify_finish_reason(
        getattr(candidate, "finish_reason", None) if candidate else None
    )
    if finish_reason and finish_reason not in {"STOP", "FINISH_REASON_STOP"}:
        raise ValueError(f"gemini_finish_reason_{finish_reason.lower()}")

    raw_text = getattr(response, "text", "") or ""
    try:
        return parse_json_object_response(raw_text, error_code)
    except json.JSONDecodeError as exc:
        raise ValueError(invalid_json_error_code) from exc
