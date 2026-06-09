from __future__ import annotations

import json
from typing import Any


def require_env_value(name: str, value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def parse_json_object_response(text: str, error_code: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(error_code)
    return parsed
