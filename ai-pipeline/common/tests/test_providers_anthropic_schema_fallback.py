from __future__ import annotations

from unittest.mock import MagicMock, patch

from common.llm_response import LlmResponse
from common.providers import (
    call_llm_detailed,
    collect_unsupported_schema_keywords,
    provider_runtime_config,
    resolve_anthropic_structured_output,
)


def test_collect_unsupported_schema_keywords_detects_one_of() -> None:
    schema = {
        "type": "object",
        "properties": {
            "directives": {
                "type": "array",
                "items": {"oneOf": [{"type": "object"}, {"type": "object"}]},
            }
        },
    }
    assert collect_unsupported_schema_keywords(schema, provider="anthropic") == [
        "oneOf"
    ]


def test_collect_unsupported_schema_keywords_detects_min_items_gt_one() -> None:
    schema = {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "object"},
            }
        },
    }
    assert collect_unsupported_schema_keywords(schema, provider="anthropic") == [
        "minItems>1"
    ]


def test_resolve_anthropic_structured_output_fallback_for_one_of() -> None:
    schema = {"oneOf": [{"type": "object"}]}
    resolved, meta = resolve_anthropic_structured_output(schema)
    assert resolved is None
    assert meta["structured_output_mode"] == "prompt_only"
    assert meta["structured_output_provider_fallback"] == "anthropic_unsupported_schema"
    assert meta["structured_output_unsupported_keywords"] == ["oneOf"]


def test_resolve_anthropic_structured_output_fallback_for_min_items_gt_one() -> None:
    schema = {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "minItems": 3,
                "items": {"type": "object"},
            }
        },
    }
    resolved, meta = resolve_anthropic_structured_output(schema)
    assert resolved is None
    assert meta["structured_output_mode"] == "prompt_only"
    assert meta["structured_output_provider_fallback"] == "anthropic_unsupported_schema"
    assert meta["structured_output_unsupported_keywords"] == ["minItems>1"]


def test_call_anthropic_omits_output_config_when_schema_has_one_of() -> None:
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array"}},
        "oneOf": [{"required": ["items"]}],
    }
    with (
        patch("anthropic.Anthropic") as mock_anthropic_cls,
        patch("common.providers._require_api_key", return_value="test-key"),
        patch(
            "common.providers.provider_runtime_config",
            return_value=provider_runtime_config("anthropic"),
        ),
        patch("common.providers._resolve_max_output_tokens", return_value=1024),
        patch(
            "common.providers._anthropic_message_text",
            return_value='{"items": []}',
        ),
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        result = call_llm_detailed(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            system="system",
            user="user",
            output_schema=schema,
        )

    kwargs = mock_client.messages.create.call_args.kwargs
    assert "output_config" not in kwargs
    assert isinstance(result, LlmResponse)
    assert result.request_params["structured_output_mode"] == "prompt_only"
    assert result.request_params["structured_output_provider_fallback"] == (
        "anthropic_unsupported_schema"
    )


def test_call_anthropic_omits_output_config_when_schema_has_min_items_gt_one() -> None:
    schema = {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "minItems": 5,
                "items": {"type": "object"},
            }
        },
        "required": ["assignments"],
        "additionalProperties": False,
    }
    with (
        patch("anthropic.Anthropic") as mock_anthropic_cls,
        patch("common.providers._require_api_key", return_value="test-key"),
        patch(
            "common.providers.provider_runtime_config",
            return_value=provider_runtime_config("anthropic"),
        ),
        patch("common.providers._resolve_max_output_tokens", return_value=1024),
        patch(
            "common.providers._anthropic_message_text",
            return_value='{"assignments": []}',
        ),
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        result = call_llm_detailed(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            system="system",
            user="user",
            output_schema=schema,
        )

    kwargs = mock_client.messages.create.call_args.kwargs
    assert "output_config" not in kwargs
    assert isinstance(result, LlmResponse)
    assert result.request_params["structured_output_mode"] == "prompt_only"
    assert result.request_params["structured_output_provider_fallback"] == (
        "anthropic_unsupported_schema"
    )
    assert result.request_params["structured_output_unsupported_keywords"] == [
        "minItems>1"
    ]


def test_call_anthropic_passes_output_config_for_simple_schema() -> None:
    schema = {
        "type": "object",
        "properties": {"assignments": {"type": "array"}},
        "required": ["assignments"],
        "additionalProperties": False,
    }
    with (
        patch("anthropic.Anthropic") as mock_anthropic_cls,
        patch("common.providers._require_api_key", return_value="test-key"),
        patch(
            "common.providers.provider_runtime_config",
            return_value=provider_runtime_config("anthropic"),
        ),
        patch("common.providers._resolve_max_output_tokens", return_value=1024),
        patch(
            "common.providers._anthropic_message_text",
            return_value='{"assignments": []}',
        ),
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        result = call_llm_detailed(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            system="system",
            user="user",
            output_schema=schema,
        )

    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": schema}
    }
    assert result.request_params["structured_output_mode"] == "json_schema"
