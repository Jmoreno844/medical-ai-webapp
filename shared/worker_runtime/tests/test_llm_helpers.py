from __future__ import annotations

from types import SimpleNamespace

import pytest

from worker_runtime.llm.common import parse_json_object_response, require_env_value
from worker_runtime.llm.google import parse_gemini_json_object_response


def test_require_env_value_rejects_empty() -> None:
    with pytest.raises(ValueError):
        require_env_value("OPENAI_API_KEY", " ")


def test_parse_json_object_response_requires_object() -> None:
    with pytest.raises(ValueError):
        parse_json_object_response("[]", "not_object")


def test_parse_gemini_json_object_response_rejects_max_tokens() -> None:
    response = SimpleNamespace(
        text='{"mentions": []}',
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="MAX_TOKENS"))],
    )

    with pytest.raises(ValueError, match="gemini_finish_reason_max_tokens"):
        parse_gemini_json_object_response(response, error_code="not_object")


def test_parse_gemini_json_object_response_rejects_invalid_json() -> None:
    response = SimpleNamespace(
        text='{"mentions": [',
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))],
    )

    with pytest.raises(ValueError, match="gemini_response_invalid_json"):
        parse_gemini_json_object_response(response, error_code="not_object")
