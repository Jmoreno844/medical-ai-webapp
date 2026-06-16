from __future__ import annotations

from unittest.mock import MagicMock, patch

from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import call_llm_detailed, provider_runtime_config


def test_call_anthropic_passes_output_config_when_schema_provided() -> None:
    schema = {
        "type": "object",
        "properties": {"assignments": {"type": "array"}},
        "required": ["assignments"],
        "additionalProperties": False,
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"assignments": []}')]

    with (
        patch("anthropic.Anthropic") as mock_anthropic_cls,
        patch(
            "document_pipeline_core.common.providers._require_api_key",
            return_value="test-key",
        ),
        patch(
            "document_pipeline_core.common.providers.provider_runtime_config",
            return_value=provider_runtime_config("anthropic"),
        ),
        patch(
            "document_pipeline_core.common.providers._resolve_max_output_tokens",
            return_value=1024,
        ),
        patch(
            "document_pipeline_core.common.providers._anthropic_message_text",
            return_value='{"assignments": []}',
        ),
    ):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_cls.return_value = mock_client

        result = call_llm_detailed(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            system="system",
            user="user",
            output_schema=schema,
        )

    assert isinstance(result, LlmResponse)
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["output_config"] == {
        "format": {
            "type": "json_schema",
            "schema": schema,
        }
    }


def test_call_anthropic_omits_output_config_without_schema() -> None:
    with (
        patch("anthropic.Anthropic") as mock_anthropic_cls,
        patch(
            "document_pipeline_core.common.providers._require_api_key",
            return_value="test-key",
        ),
        patch(
            "document_pipeline_core.common.providers.provider_runtime_config",
            return_value=provider_runtime_config("anthropic"),
        ),
        patch(
            "document_pipeline_core.common.providers._resolve_max_output_tokens",
            return_value=1024,
        ),
        patch(
            "document_pipeline_core.common.providers._anthropic_message_text",
            return_value='{"assignments": []}',
        ),
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        call_llm_detailed(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            system="system",
            user="user",
        )

    kwargs = mock_client.messages.create.call_args.kwargs
    assert "output_config" not in kwargs


def test_call_openai_respects_json_mode_false_override() -> None:
    with (
        patch("openai.OpenAI") as mock_openai_cls,
        patch(
            "document_pipeline_core.common.providers._require_api_key",
            return_value="test-key",
        ),
        patch(
            "document_pipeline_core.common.providers.provider_runtime_config",
            return_value=provider_runtime_config("openai"),
        ),
        patch(
            "document_pipeline_core.common.providers._resolve_openai_reasoning_effort",
            return_value=({}, {}),
        ),
        patch(
            "document_pipeline_core.common.stream_timing._consume_chat_completion_stream",
            return_value=LlmResponse(content="markdown body"),
        ) as mock_stream,
    ):
        mock_openai_cls.return_value = MagicMock()

        call_llm_detailed(
            provider="openai",
            model="gpt-4.1-mini",
            system="system",
            user="user",
            json_mode=False,
        )

    kwargs = mock_stream.call_args.kwargs["kwargs"]
    assert "response_format" not in kwargs
